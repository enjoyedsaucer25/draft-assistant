# backend/ingest/sources/fantasypros_ecr.py
import io
import re
import unicodedata
import urllib.parse as up
import pandas as pd
import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from ... import models

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# --- Normalizers -------------------------------------------------------------

TEAM_MAP = {
    # common cross-site differences
    "JAX": "JAC",
    "WSH": "WAS",
    "LA": "LAR",     # sometimes appears for Rams
    "STL": "LAR",    # old Rams
    "SD": "LAC",     # old Chargers
    "OAK": "LV",     # old Raiders
    "TB": "TB",      # normalize anyway
    "NO": "NO",      # Saints sometimes "NOR" → keep as "NO" since Sleeper uses "NO"
    "NOR": "NO",
    "NEP": "NE",
    "GBP": "GB",
    "SFO": "SF",
    "KCC": "KC",
    "JAC": "JAC",    # idempotent
    "WAS": "WAS",
    "LV": "LV",
    "LAC": "LAC",
    "LAR": "LAR",
    "SF": "SF",
    "KC": "KC",
    "GB": "GB",
    "NE": "NE",
}

def norm_space(s: str | None) -> str | None:
    if s is None:
        return None
    # collapse weird spaces/diacritics
    s = unicodedata.normalize("NFKC", str(s))
    s = s.replace("\xa0", " ").strip()
    return re.sub(r"\s+", " ", s)

def norm_pos(pos: str | None) -> str | None:
    if not pos:
        return None
    p = norm_space(pos).upper()
    if p in ("DST", "D/ST", "D-ST", "DEFENSE"):
        return "DEF"
    return p

def norm_team(team: str | None) -> str | None:
    if not team:
        return None
    t = norm_space(team).upper()
    return TEAM_MAP.get(t, t)

def _clean_float(val):
    if val is None:
        return None
    s = str(val).strip()
    if s == "" or s == "-":
        return None
    try:
        if pd.isna(val):
            return None
    except Exception:
        pass
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

# --- Write helpers -----------------------------------------------------------

def _ensure_consensus_row(db: Session, season: int, player_id: str, ecr_rank, ecr_pos_rank, tier, source="fantasypros"):
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

# --- CSV/HTML detection ------------------------------------------------------

def _detect_cols(df: pd.DataFrame):
    def find_col(pred):
        for c in df.columns:
            if pred(c):
                return c
        return None
    name_col = find_col(lambda c: c.lower() in ("player", "name"))
    team_col = find_col(lambda c: c.lower() in ("team", "team.1", "tm"))
    pos_col  = find_col(lambda c: c.lower() in ("pos", "position"))
    ecr_col  = find_col(lambda c: "ecr" in c.lower() or c.lower() in ("rank", "overall"))
    posr_col = find_col(lambda c: ("pos" in c.lower()) and ("rank" in c.lower()))
    tier_col = find_col(lambda c: "tier" in c.lower())
    return name_col, team_col, pos_col, ecr_col, posr_col, tier_col

# --- Matching logic ----------------------------------------------------------

def _match_player(db: Session, name: str, pos: str | None, team: str | None):
    P = models.Player
    # 1) name + pos + team
    if pos and team:
        p = db.query(P).filter(
            P.clean_name == name,
            P.position == pos,
            P.team == team
        ).first()
        if p: return p
    # 2) name + pos
    if pos:
        p = db.query(P).filter(
            P.clean_name == name,
            P.position == pos
        ).first()
        if p: return p
    # 3) name only
    p = db.query(P).filter(P.clean_name == name).first()
    return p

def _ingest_ecr_df(db: Session, season: int, df: pd.DataFrame) -> dict:
    name_col, team_col, pos_col, ecr_col, posr_col, tier_col = _detect_cols(df)
    if not name_col:
        return {"imported": 0, "matched": 0, "unmatched": 0, "unmatched_examples": [], "errors": ["CSV missing 'Player'/'Name' column"]}

    total_rows = 0
    matched = 0
    unmatched_examples = []

    for _, r in df.iterrows():
        raw_name = r[name_col]
        if pd.isna(raw_name):
            continue
        total_rows += 1

        name = norm_space(raw_name)
        team = norm_team(r.get(team_col) or r.get("team") or None)
        pos  = norm_pos(r.get(pos_col) or r.get("Position") or None)

        ecr = r.get(ecr_col)
        pos_rank = r.get(posr_col)
        tier = r.get(tier_col)

        p = _match_player(db, name, pos, team)
        if not p:
            if len(unmatched_examples) < 12:
                unmatched_examples.append({
                    "name": name, "pos": pos, "team": team,
                    "hint": "Check Sleeper import & team/pos normalization"
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
    Try to coerce a FantasyPros rankings URL into a CSV download.
    We attempt:
      - original URL as-is (in case it already returns CSV)
      - add `csv=1`
      - add `export=csv`
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
    headers = {"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml"}
    with httpx.Client(timeout=60, follow_redirects=True, headers=headers) as client:
        html = client.get(url).text

    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if not table:
        return {"imported": 0, "matched": 0, "unmatched": 0, "unmatched_examples": [], "errors": ["No table found (page may be JS-rendered). Try CSV mode."]}

    total_rows = 0
    matched = 0
    unmatched_examples = []

    rows = table.find_all("tr")
    for tr in rows:
        cols = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if len(cols) < 4:
            continue
        rank = _clean_float(cols[0])
        if rank is None:
            continue

        total_rows += 1
        name = norm_space(cols[1])
        team = norm_team(cols[2] if len(cols) > 2 else None)
        pos = norm_pos(cols[3] if len(cols) > 3 else None)
        tier = None
        for c in cols:
            if isinstance(c, str) and c.lower().startswith("tier"):
                m = re.search(r"(\d+)", c)
                if m:
                    tier = int(m.group(1))

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
        return import_fp_overall_html(db, season, path_or_url)
    else:
        return import_fp_csv(db, season, path_or_url)
