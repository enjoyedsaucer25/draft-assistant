import pandas as pd, httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from ... import models

def _upsert_adp(db: Session, season: int, player_id: str, source: str, adp, rank):
    row = db.query(models.ADP).filter_by(season=season, player_id=player_id, source=source).first()
    if not row:
        row = models.ADP(season=season, player_id=player_id, source=source)
        db.add(row)
    row.adp = float(adp) if adp is not None else row.adp
    row.rank = float(rank) if rank is not None else row.rank

def import_fp_adp_csv(db: Session, season: int, csv_path: str, source_name="fp_composite") -> dict:
    df = pd.read_csv(csv_path)
    name_col = next((c for c in df.columns if c.lower() in ("player","name")), None)
    adp_col = next((c for c in df.columns if "adp" in c.lower()), None)
    if not (name_col and adp_col):
        return {"imported": 0, "errors": ["CSV missing Player/ADP columns"]}
    count = 0
    for _, r in df.iterrows():
        name = str(r[name_col]).strip()
        team = str(r.get("Team") or "").strip() or None
        pos = str(r.get("Pos") or "").strip() or None
        adp = r[adp_col]
        rank = r.get("Rank") or None
        q = db.query(models.Player).filter(models.Player.clean_name==name)
        if pos: q = q.filter(models.Player.position==pos)
        if team: q = q.filter(models.Player.team==team)
        p = q.first()
        if not p: 
            continue
        _upsert_adp(db, season, p.player_id, source_name, adp, rank)
        count += 1
    db.commit()
    return {"imported": count, "errors": []}
