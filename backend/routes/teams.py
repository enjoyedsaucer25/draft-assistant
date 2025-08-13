from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..db import get_db
from .. import models, schemas

router = APIRouter(prefix="/teams", tags=["teams"])

@router.post("/init", response_model=list[schemas.TeamOut])
def init_teams(db: Session = Depends(get_db)):
    created = []
    for i in range(1, 13):
        t = db.query(models.TeamLeague).filter_by(team_slot_id=i).first()
        if not t:
            t = models.TeamLeague(team_slot_id=i, team_name=f"Team {i}", draft_position=i)
            db.add(t)
        else:
            t.draft_position = t.draft_position or i
        created.append(t)
    db.commit()
    return created

@router.get("", response_model=list[schemas.TeamOut])
def list_teams(db: Session = Depends(get_db)):
    return db.query(models.TeamLeague).order_by(models.TeamLeague.team_slot_id.asc()).all()

@router.post("/upsert", response_model=schemas.TeamOut)
def upsert_team(payload: schemas.TeamIn, db: Session = Depends(get_db)):
    t = db.query(models.TeamLeague).filter_by(team_slot_id=payload.team_slot_id).first()
    if not t:
        t = models.TeamLeague(**payload.model_dump())
        db.add(t)
    else:
        t.team_name = payload.team_name
        t.draft_position = payload.draft_position
    db.commit(); db.refresh(t)
    return t
