from __future__ import annotations

import csv
import os
import re
import math
from difflib import SequenceMatcher
from typing import Any, Optional, Tuple, List

from sqlalchemy.orm import Session

from .. import models

# -----------------------------
# Normalization / parsing utils
# -----------------------------
_NUM_KEEP = re.compile(r"[-+0-9eE\.]+")

def to_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, float):
        if math.isnan(val):
            return None
        return val
    if isinstance(val, (int, bool)):
        return float(val)
    if isinstance(val, str):
        s = val.strip()
        if not s or s.lower() in {"na", "nan", "null", "none", "--"}:
            return None
        s = s.replace(",", "")
        m = _NUM_KEEP.search(s)
        if not m:
            return None
        try:
            return float(m.group(0))
        except Exception:
            return None
    return None

def to_int(val: Any) -> Optional[int]:
    if val is None:
        return None
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        if math.isnan(val):
            return None
        try:
            return int(val)
        except Exception:
            return None
    if isinstance(val, str):
        s = val.strip()
        if not s or s.lower() in {"na", "nan", "null", "none", "--"}:
            return None
        s = s.replace(",", "")
        m = re.search(r"-?\d+", s)
        if not m:
            return None
        try:
            return int(m.group(0))
        except Exception:
            return None
    return None

def _norm_name(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\s]", "", s)  # remove punctuation/apostrophes/dots
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _last_name(norm_name: str) -> str:
    parts = norm_name.split()
    return parts[-1] if parts else norm_name

def _first_initial(norm_name: str) -> Optional[str]:
    parts = norm_name.split()
    return parts[0][0] if parts else None

def _canon_pos(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    p = re.sub(r"\d+$", "", s.strip().upper())
    if p == "DST":
        return "DEF"
    if p == "PK":
        return "K"
    return p

def _key(source_name: str, pos: Optional[str], team: Optional[str] = None) -> str:
    base = f"{_norm_name(source_name)}|{_canon_pos(pos) or ''}"
    if team:
        base += f"|{team.upper()}"
    return base

# FantasyPros ADP has "Name TEAM (BYE)" in player_name; strip trailing team/bye.
_TEAM_BYE_TRAIL = re.compile(r"\s+[A-Z]{2,3}\s*\(\d{1,2}\)\s*$")
def strip_fp_team_bye(name_with_team: str) -> str:
    return _TEAM_BYE_TRAIL.sub("", name_with_team or "").strip()

# Common alias fixes
ALIAS_MAP = {
    "tank dell": "nathaniel dell",
    "tutu atwell": "chatarius atwell",
    "hollywood brown": "marquise brown",
}

# -----------------------------
# Crosswalk resolution
# -----------------------------
def _resolve_player_id(
    db: Session,
    season: int,
    source: str,
    source_name: str,
    pos: Optional[str],
    team: Optional[str] = None,
) -> Tuple[Optional[str], float, str]:
    """Robust resolver with crosswalk -> exact -> last-name/initial -> fuzzy."""
    pos_c = _canon_pos(pos)
    name_norm = _norm_name(source_name)
    name_norm = ALIAS_MAP.get(name_norm, name_norm)

    key_team = _key(source_name, pos_c, team)
    key_basic = _key(source_name, pos_c, None)

    xw = (
        db.query(models.PlayerXWalk)
        .filter_by(season=season, source=source, source_key=key_team)
        .first()
    )
    if xw:
        return xw.player_id, xw.confidence, "crosswalk(team)"

    xw = (
        db.query(models.PlayerXWalk)
        .filter_by(season=season, source=source, source_key=key_basic)
        .first()
    )
    if xw:
        return xw.player_id, xw.confidence, "crosswalk(basic)"

    cands: List[models.Player] = (
        db.query(models.Player)
        .filter(models.Player.season == season, models.Player.position == (pos_c or ""))
        .all()
    )

    exact = [p for p in cands if _norm_name(p.clean_name) == name_norm]
    if len(exact) == 1:
        pid = exact[0].player_id
        db.add(models.PlayerXWalk(season=season, source=source, source_key=key_basic, player_id=pid, confidence=1.0))
        db.commit()
        return pid, 1.0, "deterministic(name+pos)"

    ln = _last_name(name_norm)
    by_ln = [p for p in cands if _last_name(_norm_name(p.clean_name)) == ln]
    if team:
        by_ln_team = [p for p in by_ln if (p.team or "").upper() == team.upper()]
        if len(by_ln_team) == 1:
            pid = by_ln_team[0].player_id
            db.add(models.PlayerXWalk(season=season, source=source, source_key=key_team, player_id=pid, confidence=0.98))
            db.commit()
            return pid, 0.98, "lastname+team"

    fi = _first_initial(name_norm)
    if fi:
        by_ln_fi = [p for p in by_ln if _first_initial(_norm_name(p.clean_name)) == fi]
        if len(by_ln_fi) == 1:
            pid = by_ln_fi[0].player_id
            db.add(models.PlayerXWalk(season=season, source=source, source_key=key_basic, player_id=pid, confidence=0.96))
            db.commit()
            return pid, 0.96, "lastname+firstinitial"

    from difflib import SequenceMatcher
    def score(p: models.Player) -> float:
        return SequenceMatcher(a=name_norm, b=_norm_name(p.clean_name)).ratio()

    best = None
    best_s = 0.0
    for p in by_ln if by_ln else cands:
        s = score(p)
        if s > best_s:
            best_s, best = s, p
    if best and best_s >= 0.85:
        pid = best.player_id
        db.add(models.PlayerXWalk(season=season, source=source, source_key=key_basic, player_id=pid, confidence=float(round(best_s, 3))))
        db.commit()
        return pid, float(round(best_s, 3)), "fuzzy"

    return None, 0.0, "unresolved"

# -----------------------------
# Imports from normalized CSVs
# -----------------------------
def import_fp_ecr_csv_to_orm(csv_path: str, db: Session, season: int) -> dict:
    if not os.path.exists(csv_path):
        return {"imported": 0, "unmatched": 0, "errors": [f"missing {csv_path}"]}

    imported = 0
    unmatched = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        hdr = {h.lower().strip(): h for h in (reader.fieldnames or [])}

        def pick(*names: str) -> Optional[str]:
            for n in names:
                if n in hdr:
                    return hdr[n]
            return None

        c_name = pick("player_name", "player", "name", "player/team", "player (team)")
        c_rank = pick("rank", "rk", "ecr")
        c_tier = pick("tier", "tiers")
        c_pos  = pick("pos", "position")
        c_team = pick("team")

        for row in reader:
            name = (row.get(c_name) or "").strip() if c_name else ""
            if not name:
                continue
            pos  = (row.get(c_pos) or "").strip() if c_pos else ""
            team = (row.get(c_team) or "").strip() if c_team else ""
            team = team or None

            pid, _, _ = _resolve_player_id(db, season, "fantasypros", name, pos, team)
            if not pid:
                unmatched += 1
                continue

            ecr  = to_float(row.get(c_rank) if c_rank else None)
            tier = to_int(row.get(c_tier) if c_tier else None)

            cr = db.query(models.ConsensusRank).filter_by(season=season, player_id=pid, source="fantasypros").first()
            if not cr:
                cr = models.ConsensusRank(
                    season=season,
                    player_id=pid,
                    ecr_rank=ecr,
                    ecr_pos_rank=None,
                    tier=tier,
                    source="fantasypros",
                )
                db.add(cr)
            else:
                if ecr is not None:
                    cr.ecr_rank = ecr
                if tier is not None:
                    cr.tier = tier

            imported += 1

    db.commit()
    return {"imported": imported, "unmatched": unmatched, "errors": []}

def import_fp_adp_csv_to_orm(csv_path: str, db: Session, season: int) -> dict:
    if not os.path.exists(csv_path):
        return {"imported": 0, "unmatched": 0, "errors": [f"missing {csv_path}"]}

    imported = 0
    unmatched = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        hdr = {h.lower().strip(): h for h in (reader.fieldnames or [])}

        def pick(*names: str) -> Optional[str]:
            for n in names:
                if n in hdr:
                    return hdr[n]
            return None

        c_name  = pick("player_name", "player", "name", "player/team", "player (team)")
        c_pos   = pick("pos", "position")
        c_team  = pick("team")
        c_adp   = pick("adp_avg", "adp", "avg_draft_pos", "average draft position", "average_draft_position")
        c_posrk = pick("pos_rank", "adp_pos_rank")
        c_ss    = pick("sample_size", "samples")

        for row in reader:
            raw = (row.get(c_name) or "").strip() if c_name else ""
            if not raw:
                continue
            name = strip_fp_team_bye(raw)

            pos  = (row.get(c_pos) or "").strip() if c_pos else ""
            team = (row.get(c_team) or "").strip() if c_team else ""
            team = team or None

            pid, _, _ = _resolve_player_id(db, season, "fantasypros", name, pos, team)
            if not pid:
                unmatched += 1
                continue

            adp          = to_float(row.get(c_adp) if c_adp else None)
            adp_pos_rank = to_float(row.get(c_posrk) if c_posrk else None)
            ss           = to_int(row.get(c_ss) if c_ss else None)

            rec = db.query(models.ADP).filter_by(season=season, player_id=pid, source="fantasypros").first()
            if not rec:
                rec = models.ADP(
                    season=season,
                    player_id=pid,
                    source="fantasypros",
                    adp=adp,
                    adp_pos_rank=adp_pos_rank,
                    sample_size=ss,
                )
                db.add(rec)
            else:
                if adp is not None:
                    rec.adp = adp
                if adp_pos_rank is not None:
                    rec.adp_pos_rank = adp_pos_rank
                if ss is not None:
                    rec.sample_size = ss

            imported += 1

    db.commit()
    return {"imported": imported, "unmatched": unmatched, "errors": []}

def import_fp_proj_csv_to_orm(csv_path: str, db: Session, season: int) -> dict:
    """
    Import FP projections. If 'pts' is missing, compute Half-PPR fantasy points from components:
      pass: 0.04*pass_yd + 4*pass_td - 2*pass_int
      rush: 0.1*rush_yd + 6*rush_td
      rec : 0.5*rec + 0.1*rec_yd + 6*rec_td
    Apply 'thousands' correction ONLY to pass_yd and rec_yd.
    """
    if not os.path.exists(csv_path):
        return {"imported": 0, "unmatched": 0, "errors": [f"missing {csv_path}"]}

    imported = 0
    unmatched = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        hdr = {h.lower().strip(): h for h in (reader.fieldnames or [])}

        def pick(*names: str) -> Optional[str]:
            for n in names:
                if n in hdr:
                    return hdr[n]
            return None

        c_name  = pick("player_name", "player", "name", "player/team", "player (team)")
        c_pos   = pick("pos", "position")
        c_team  = pick("team")

        c_pts      = pick("pts", "fantasy_points", "proj_pts", "points", "fpts")
        c_pass_yd  = pick("pass_yd", "pass_yds", "pass_yards")
        c_pass_td  = pick("pass_td", "pass_tds")
        c_pass_int = pick("pass_int", "ints", "int", "interceptions", "pass_interceptions")
        c_rush_yd  = pick("rush_yd", "rush_yds", "rush_yards")
        c_rush_td  = pick("rush_td", "rush_tds")
        c_rec      = pick("rec", "receptions")
        c_rec_yd   = pick("rec_yd", "rec_yds", "rec_yards")
        c_rec_td   = pick("rec_td", "rec_tds")

        for row in reader:
            name = (row.get(c_name) or "").strip() if c_name else ""
            if not name:
                continue
            pos  = (row.get(c_pos) or "").strip() if c_pos else ""
            team = (row.get(c_team) or "").strip() if c_team else ""
            team = team or None

            pid, _, _ = _resolve_player_id(db, season, "fantasypros", name, pos, team)
            if not pid:
                unmatched += 1
                continue

            rec_obj = db.query(models.Projection).filter_by(season=season, player_id=pid, source="fantasypros").first()
            if not rec_obj:
                rec_obj = models.Projection(season=season, player_id=pid, source="fantasypros")
                db.add(rec_obj)

            # components
            pass_yd  = to_float(row.get(c_pass_yd)) if c_pass_yd else None
            pass_td  = to_float(row.get(c_pass_td)) if c_pass_td else None
            pass_int = to_float(row.get(c_pass_int)) if c_pass_int else None
            rush_yd  = to_float(row.get(c_rush_yd)) if c_rush_yd else None
            rush_td  = to_float(row.get(c_rush_td)) if c_rush_td else None
            recs     = to_float(row.get(c_rec))     if c_rec     else None
            rec_yd   = to_float(row.get(c_rec_yd))  if c_rec_yd  else None
            rec_td   = to_float(row.get(c_rec_td))  if c_rec_td  else None

            # thousands correction: pass_yd & rec_yd only
            if pass_yd is not None and pass_yd < 50:
                pass_yd *= 1000.0
            if rec_yd is not None and rec_yd < 50:
                rec_yd *= 1000.0

            # save components
            if pass_yd is not None:  rec_obj.pass_yd = pass_yd
            if pass_td is not None:  rec_obj.pass_td = pass_td
            if rush_yd is not None:  rec_obj.rush_yd = rush_yd
            if rush_td is not None:  rec_obj.rush_td = rush_td
            if recs is not None:     rec_obj.rec     = recs
            if rec_yd is not None:   rec_obj.rec_yd  = rec_yd
            if rec_td is not None:   rec_obj.rec_td  = rec_td

            # compute points if missing
            pts = to_float(row.get(c_pts)) if c_pts else None
            if pts is None:
                pyd  = pass_yd or 0.0
                ptd  = pass_td or 0.0
                pint = pass_int or 0.0
                ryd  = rush_yd or 0.0
                rtd  = rush_td or 0.0
                r    = recs or 0.0
                ryd2 = rec_yd or 0.0
                rtd2 = rec_td or 0.0
                pts = round(
                    0.04 * pyd + 4.0 * ptd - 2.0 * pint +
                    0.1  * ryd + 6.0 * rtd +
                    0.5  * r   + 0.1  * ryd2 + 6.0 * rtd2,
                    1,
                )

            rec_obj.pts = pts
            imported += 1

    db.commit()
    return {"imported": imported, "unmatched": unmatched, "errors": []}
