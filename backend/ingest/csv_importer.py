import pandas as pd
from sqlalchemy.orm import Session
from .. import models

def upsert_player_and_rank(row, db: Session):
    # Upsert Player
    p = db.query(models.Player).get(row["player_id"])
    if not p:
        p = models.Player(
            player_id=row["player_id"],
            season=int(row["season"]),
            clean_name=row["clean_name"],
            position=row["position"],
            team=row.get("team"),
            bye_week=int(row["bye_week"]) if pd.notna(row.get("bye_week")) else None,
        )
        db.add(p)
    else:
        # update basics (safe fields)
        p.season = int(row["season"])
        p.clean_name = row["clean_name"]
        p.position = row["position"]
        p.team = row.get("team")
        p.bye_week = int(row["bye_week"]) if pd.notna(row.get("bye_week")) else None

    # Upsert ConsensusRank
    cr = db.query(models.ConsensusRank).filter_by(
        season=int(row["season"]), player_id=row["player_id"]).first()
    if not cr:
        cr = models.ConsensusRank(
            season=int(row["season"]),
            player_id=row["player_id"],
            ecr_rank=float(row["ecr_rank"]) if pd.notna(row.get("ecr_rank")) else None,
            ecr_pos_rank=float(row["ecr_pos_rank"]) if pd.notna(row.get("ecr_pos_rank")) else None,
            tier=int(row["tier"]) if pd.notna(row.get("tier")) else None,
            source="seed_csv"
        )
        db.add(cr)
    else:
        cr.ecr_rank = float(row["ecr_rank"]) if pd.notna(row.get("ecr_rank")) else cr.ecr_rank
        cr.ecr_pos_rank = float(row["ecr_pos_rank"]) if pd.notna(row.get("ecr_pos_rank")) else cr.ecr_pos_rank
        cr.tier = int(row["tier"]) if pd.notna(row.get("tier")) else cr.tier
        cr.source = "seed_csv"

def import_from_csv(csv_path: str, db: Session) -> dict:
    df = pd.read_csv(csv_path)
    required = {"player_id","season","clean_name","position"}
    missing = required - set(df.columns)
    if missing:
        return {"imported": 0, "errors": [f"Missing columns: {', '.join(sorted(missing))}"]}

    count = 0
    for _, row in df.iterrows():
        upsert_player_and_rank(row, db)
        count += 1
    db.commit()
    return {"imported": count, "errors": []}
