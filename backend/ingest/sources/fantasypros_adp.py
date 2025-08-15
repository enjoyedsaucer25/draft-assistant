import pandas as pd
from sqlalchemy.orm import Session
from ... import models

def _clean_float(val):
    # Treat NaN / empty / dash as None; otherwise cast to float
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

def _upsert_adp(db: Session, season: int, player_id: str, source: str, adp, rank, sample_size=None):
    row = db.query(models.ADP).filter_by(season=season, player_id=player_id, source=source).first()
    if not row:
        row = models.ADP(season=season, player_id=player_id, source=source)
        db.add(row)
    adp_clean = _clean_float(adp)
    rank_clean = _clean_float(rank)
    row.adp = adp_clean if adp_clean is not None else row.adp
    row.rank = rank_clean if rank_clean is not None else row.rank
    if hasattr(row, "sample_size") and sample_size is not None:
        try:
            row.sample_size = int(sample_size)
        except Exception:
            pass

def import_fp_adp_csv(db: Session, season: int, csv_path: str, source_name="fp_composite") -> dict:
    """
    Expected CSV headers (flexible):
      - Player / Name
      - Team / Tm (optional)
      - Pos / Position (optional, improves matching)
      - ADP (or any column with 'adp' in its name)
      - Rank (optional)
      - 'N' or 'Times Drafted' (optional sample size)
    """
    df = pd.read_csv(csv_path)

    def find_col(pred):
        for c in df.columns:
            if pred(c):
                return c
        return None

    name_col = find_col(lambda c: c.lower() in ("player", "name"))
    adp_col  = find_col(lambda c: "adp" in c.lower())
    team_col = find_col(lambda c: c.lower() in ("team", "tm"))
    pos_col  = find_col(lambda c: c.lower() in ("pos", "position"))
    rank_col = find_col(lambda c: "rank" in c.lower())
    n_col    = find_col(lambda c: c.lower() in ("n", "times drafted", "drafts"))

    if not (name_col and adp_col):
        return {"imported": 0, "errors": ["CSV missing Player/ADP columns"]}

    count = 0
    for _, r in df.iterrows():
        name = str(r[name_col]).strip()
        if not name:
            continue
        team = str(r.get(team_col) or "").strip() or None
        pos  = str(r.get(pos_col) or "").strip() or None
        adp  = r.get(adp_col)
        rank = r.get(rank_col)
        n    = r.get(n_col)

        # Match by name; refine with pos/team if available
        q = db.query(models.Player).filter(models.Player.clean_name == name)
        if pos:
            q = q.filter(models.Player.position == pos)
        if team:
            q = q.filter(models.Player.team == team)
        p = q.first()
        if not p:
            # If strict match fails, try name-only fallback (still may be wrong, but better coverage)
            p = db.query(models.Player).filter(models.Player.clean_name == name).first()
        if not p:
            continue

        _upsert_adp(db, season, p.player_id, source_name, adp, rank, n)
        count += 1

    db.commit()
    return {"imported": count, "errors": []}
