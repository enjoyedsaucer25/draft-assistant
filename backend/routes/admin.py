from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
import os
from ..db import get_db
from ..config.settings import settings
from ..ingest.csv_importer import import_from_csv
from .. import models

router = APIRouter(prefix="/admin", tags=["admin"])

def require_admin(x_token: str | None = Header(None, description="admin token for /admin/* (header name: x-token)")):
    if settings.admin_token and x_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="unauthorized")


@router.post("/import/csv", dependencies=[Depends(require_admin)])
def admin_import_csv(path: str, db: Session = Depends(get_db)):
    if not os.path.exists(path):
        raise HTTPException(status_code=400, detail=f"File not found: {path}")
    result = import_from_csv(path, db)
    if result["errors"]:
        raise HTTPException(status_code=400, detail=result)
    return {"ok": True, "result": result}

@router.post("/import/demo", dependencies=[Depends(require_admin)])
def admin_import_demo(db: Session = Depends(get_db)):
    demo = [
        {"player_id":"rb.cmcc","season":2025,"clean_name":"Christian McCaffrey","position":"RB","team":"SF","bye_week":9,"ecr_rank":1,"ecr_pos_rank":1,"tier":1},
        {"player_id":"wr.jchase","season":2025,"clean_name":"Ja'Marr Chase","position":"WR","team":"CIN","bye_week":12,"ecr_rank":2,"ecr_pos_rank":1,"tier":1},
        {"player_id":"wr.cupl","season":2025,"clean_name":"CeeDee Lamb","position":"WR","team":"DAL","bye_week":7,"ecr_rank":3,"ecr_pos_rank":2,"tier":1},
        {"player_id":"rb.brobinson","season":2025,"clean_name":"Bijan Robinson","position":"RB","team":"ATL","bye_week":12,"ecr_rank":4,"ecr_pos_rank":2,"tier":1},
        {"player_id":"wr.asb","season":2025,"clean_name":"Amon-Ra St. Brown","position":"WR","team":"DET","bye_week":9,"ecr_rank":5,"ecr_pos_rank":3,"tier":1},
        {"player_id":"qb.jallen","season":2025,"clean_name":"Josh Allen","position":"QB","team":"BUF","bye_week":12,"ecr_rank":20,"ecr_pos_rank":1,"tier":2},
    ]
    for r in demo:
        p = db.query(models.Player).filter_by(player_id=r["player_id"]).first()
        if not p:
            db.add(models.Player(**{k:r[k] for k in ["player_id","season","clean_name","position","team","bye_week"]}))
        else:
            p.season=r["season"]; p.clean_name=r["clean_name"]; p.position=r["position"]; p.team=r["team"]; p.bye_week=r["bye_week"]
        cr = db.query(models.ConsensusRank).filter_by(season=r["season"], player_id=r["player_id"]).first()
        if not cr:
            db.add(models.ConsensusRank(season=r["season"], player_id=r["player_id"], ecr_rank=r["ecr_rank"], ecr_pos_rank=r["ecr_pos_rank"], tier=r["tier"], source="demo"))
        else:
            cr.ecr_rank=r["ecr_rank"]; cr.ecr_pos_rank=r["ecr_pos_rank"]; cr.tier=r["tier"]; cr.source="demo"
    db.commit()
    return {"ok": True, "imported": len(demo)}
