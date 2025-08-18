# backend/ingest/sources/fantasypros_ecr.py
from __future__ import annotations

import io
import re
import unicodedata
import urllib.parse as up
from typing import Optional, Tuple, cast

import pandas as pd
import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag
from sqlalchemy.orm import Session

from ... import models

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# --- Normalizers -------------------------------------------------------------

TEAM_MAP = {
    "JAX": "JAC", "WSH": "WAS", "LA": "LAR", "STL": "LAR", "SD": "LAC", "OAK": "LV",
    "NOR": "NO", "NEP": "NE", "GBP": "GB", "SFO": "SF", "KCC": "KC",
    "JAC": "JAC", "WAS": "WAS", "LV": "LV", "LAC": "LAC", "LAR": "LAR",
    "SF": "SF", "KC": "KC", "GB": "GB", "NE": "NE",
}

def norm_space(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = unicodedata.normalize("NFKC", str(s)).replace("\xa0", " ").strip()
    return re.sub(r"\s+", " ", s)

def norm_pos(pos: Optional[str]) -> Optional[str]:
    if not pos:
        return None
    # Pylance-safe: coerce to str first, then upper
    p = (norm_space(pos) or "").upper()
    if p in ("DST", "D/ST", "D-ST", "DEFENSE"):
        return "DEF"
    # strip trailing non-letters like "RB1"
    p = re.sub(r"[^A-Z]", "", p)
    return p or None

def norm_team(team: Optional[str]) -> Optional[str]:
    if not team:
        return None
    t = (norm_space(team) or "").upper()
    t = re.sub(r"[^A-Z]", "", t)  # drop punctuation
    return TEAM_MAP.get(t, t)

def _clean_float(val):
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except Exception:
        pass
    s = str(val).strip()
    if s == "" or s == "-":
        return None
    # strip trailing position suffixes like "WR1"
    s = re.sub(r"[A-Za-z]+.*$", "", s).strip()
    try:
        return float(s)
    except Exception:
        return None

def _clean_int(val):
    f = _clean_float(val)
    try:
        return int(f) if f is not None else None
    except Exception:
        return None

# --- Helpers for writing rows ------------------------------------------------

def _ensure_consensus_row(
    db: Session,
    season: int,
    player_id: str,
    ecr_rank,
    ecr_pos_rank,
    tier,
    source: str = "fantasypros",
):
    cr = db.query(models.ConsensusRank).filter_by(season=season, player_id=player_id).first()
    if not cr:
        cr = models.ConsensusRank(season=season, player_id=player_id)
        db.add(cr)
    ecr_clean  = _clean_float(ecr_rank)
    epos_clean = _clean_float(ecr_pos_rank)
    tier_clean = _clean_int(tier)
    if ecr_clean is not None:
        cr.ecr_rank = ecr_clean
    if epos_clean is not None:
        cr.ecr_pos_rank = epos_clean
    if tier_clean is not None:
        cr.tier = tier_clean
    cr.source = source

# --- CSV column detection / parsing -----------------------------------------

def _detect_cols(df: pd.DataFrame) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Return: (name_col, team_col, pos_col, ecr_col, posr_col, tier_col)
    Accepts common FantasyPros headers including "player_name" and "RK".
    """
    cols = [str(c) for c in df.columns]

    def find_col(pred):
        for c in cols:
            try:
                if pred(c):
                    return c
            except Exception:
                continue
        return None

    # Name can appear as "Player", "Name", "player_name", or "Player Team (Bye)"
    name_col = find_col(lambda c: c.lower() in ("player", "name", "player_name", "player name", "player_name_clean")
                                  or "player team (bye" in c.lower())

    # Team and POS often present as their own columns
    team_col = find_col(lambda c: c.lower() in ("team", "tm", "team.1"))
    pos_col  = find_col(lambda c: c.lower() in ("pos", "position"))

    # ECR/Overall rank
    ecr_col = find_col(lambda c: "ecr" in c.lower() or c.lower() in ("rk", "rank", "overall"))

    # Positional rank
    posr_col = find_col(lambda c: ("pos" in c.lower() and "rank" in c.lower())
                                  or c.lower() in ("pos rank","pos_rank","pr","posrank","position rank"))

    # Tier
    tier_col = find_col(lambda c: "tier" in c.lower() or c.lower() in ("tiers","ecr_tier","fp_tier"))

    return name_col, team_col, pos_col, ecr_col, posr_col, tier_col

# --- Matching logic ----------------------------------------------------------

def _match_player(db: Session, name: str, pos: Optional[str], team: Optional[str]):
    P = models.Player
    # try exact (name+pos+team), then name+pos, then name only
    if pos and team:
        p = db.query(P).filter(P.clean_name == name, P.position == pos, P.team == team).first()
        if p: return p
    if pos:
        p = db.query(P).filter(P.clean_name == name, P.position == pos).first()
        if p: return p
    p = db.query(P).filter(P.clean_name == name).first()
    return p

def _ingest_ecr_df(db: Session, season: int, df: pd.DataFrame) -> dict:
    # Strip fully-empty columns & whitespace in headers
    df = df.loc[:, [col for col in df.columns if not df[col].isna().all()]]
    df.rename(columns={c: norm_space(c) for c in df.columns}, inplace=True)

    name_col, team_col, pos_col, ecr_col, posr_col, tier_col = _detect_cols(df)
    if not name_col:
        return {"imported": 0, "matched": 0, "unmatched": 0, "unmatched_examples": [], "errors": ["CSV missing a recognizable Player/Name column (try 'player_name')"]}

    total_rows = 0
    matched = 0
    unmatched_examples = []

    for _, r in df.iterrows():
        raw_name = r.get(name_col)
        if pd.isna(raw_name):
            continue
        name = norm_space(str(raw_name)) or ""
        if name == "":
            continue
        total_rows += 1

        # Pull team/pos
        team = norm_team(cast(Optional[str], r.get(team_col))) if team_col else None
        pos  = norm_pos(cast(Optional[str], r.get(pos_col))) if pos_col else None

        ecr = r.get(ecr_col) if ecr_col else None
        pos_rank = r.get(posr_col) if posr_col else None
        tier = r.get(tier_col) if tier_col else None

        p = _match_player(db, name, pos, team)
        if not p:
            if len(unmatched_examples) < 12:
                unmatched_examples.append({
                    "name": name, "pos": pos, "team": team,
                    "hint": "Ensure Sleeper players imported for same season; check name/pos/team normalization."
                })
            continue

        _ensure_consensus_row(db, season, p.player_id, ecr, pos_rank, tier)
        matched += 1

    db.commit()
    return {
        "imported": matched,
        "matched": matched,
        "unmatched": max(0, total_rows - matched),
        "unmatched_examples": unmatched_examples,
        "errors": [],
    }

# --- Public entry points -----------------------------------------------------

def import_fp_csv(db: Session, season: int, csv_path: str) -> dict:
    """Local CSV path import."""
    df = pd.read_csv(csv_path)
    return _ingest_ecr_df(db, season, df)

def _try_csv_from_url(client: httpx.Client, url: str) -> bytes | None:
    """
    Best-effort CSV fetcher:
      - original URL as-is (in case it already returns CSV)
      - add csv=1
      - add export=csv
    """
    def _fetch(u):
        r = client.get(u, headers={"User-Agent": _UA})
        if r.status_code == 200 and r.text.count(",") > 10:
            return r.content
        return None

    content = _fetch(url)
    if content:
        return content

    p = up.urlparse(url)
    q = up.parse_qsl(p.query, keep_blank_values=True)
    if ("csv", "1") not in q:
        q.append(("csv", "1"))
    url_csv = up.urlunparse(p._replace(query=up.urlencode(q)))
    content = _fetch(url_csv)
    if content:
        return content

    p = up.urlparse(url)
    q = up.parse_qsl(p.query, keep_blank_values=True)
    if ("export", "csv") not in q:
        q.append(("export", "csv"))
    url_export = up.urlunparse(p._replace(query=up.urlencode(q)))
    content = _fetch(url_export)
    if content:
        return content

    return None

def import_fp_csv_from_url(db: Session, season: int, url: str) -> dict:
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        content = _try_csv_from_url(client, url)
        if not content:
            return {"imported": 0, "matched": 0, "unmatched": 0, "unmatched_examples": [], "errors": [f"No CSV available at {url}"]}
        try:
            df = pd.read_csv(io.BytesIO(content))
        except Exception as e:
            return {"imported": 0, "matched": 0, "unmatched": 0, "unmatched_examples": [], "errors": [f"CSV parse failed: {e}"]}
    return _ingest_ecr_df(db, season, df)

def import_fp_overall_html(db: Session, season: int, url: str) -> dict:
    """
    Last-resort HTML scraper. Most FP rank pages are JS-rendered.
    Prefer CSV mode (import_fp_csv_from_url). This just tries a basic table parse.
    """
    headers = {"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml"}
    with httpx.Client(timeout=60, follow_redirects=True, headers=headers) as client:
        html = client.get(url).text

    soup = BeautifulSoup(html, "lxml")
    table_el = soup.find("table")
    if not table_el or not hasattr(table_el, "find_all"):
        return {"imported": 0, "matched": 0, "unmatched": 0, "unmatched_examples": [], "errors": ["No table found (page likely JS-rendered). Use CSV mode."]}

    table = cast(Tag, table_el)
    total_rows = 0
    matched = 0
    unmatched_examples = []

    rows = table.find_all("tr")
    for tr in rows:
        # Pylance-safe: assume tr is Tag
        ttag = cast(Tag, tr)
        cols = [c.get_text(strip=True) for c in ttag.find_all(["td", "th"])]
        if len(cols) < 3:
            continue
        rank = _clean_float(cols[0])
        if rank is None:
            continue
        total_rows += 1
        name = norm_space(cols[1]) or ""
        if name == "":
            continue
        team = norm_team(cols[2] if len(cols) > 2 else None)
        pos = norm_pos(cols[3] if len(cols) > 3 else None)

        # Tier may be embedded as "Tier X" in any col
        tier = None
        for c in cols:
            if isinstance(c, str) and "tier" in c.lower():
                m = re.search(r"(\d+)", c)
                if m:
                    tier = int(m.group(1))
                    break

        p = _match_player(db, name, pos, team)
        if not p:
            if len(unmatched_examples) < 12:
                unmatched_examples.append({"name": name, "pos": pos, "team": team})
            continue

        _ensure_consensus_row(db, season, p.player_id, rank, None, tier)
        matched += 1

    db.commit()
    return {
        "imported": matched,
        "matched": matched,
        "unmatched": max(0, total_rows - matched),
        "unmatched_examples": unmatched_examples,
        "errors": [],
    }

def import_fp_ecr_auto(db: Session, season: int, path_or_url: str) -> dict:
    if re.match(r"^https?://", path_or_url, re.I):
        csv_res = import_fp_csv_from_url(db, season, path_or_url)
        if not csv_res["errors"] and csv_res["imported"] > 0:
            return csv_res
        # If CSV fetch failed, HTML is unlikely to work (JS), but include as last resort:
        html_res = import_fp_overall_html(db, season, path_or_url)
        return html_res if html_res["imported"] > 0 else csv_res
    else:
        return import_fp_csv(db, season, path_or_url)
