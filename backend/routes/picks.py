from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from .. import models, schemas

router = APIRouter(prefix="/picks", tags=["picks"])

@router.post("", response_model=schemas.PickOut)
def create_pick(payload: schemas.PickIn, db: Session = Depends(get_db)):
    if not db.query(models.Player).filter_by(player_id=payload.player_id).first():
        raise HTTPException(status_code=400, detail="Unknown player_id")
    if not db.query(models.TeamLeague).filter_by(team_slot_id=payload.team_slot_id).first():
        raise HTTPException(status_code=400, detail="Unknown team_slot_id")
    if db.query(models.Pick).filter_by(overall_no=payload.overall_no).first():
        raise HTTPException(status_code=400, detail=f"overall_no {payload.overall_no} already used")
    p = models.Pick(**payload.model_dump())
    db.add(p); db.commit(); db.refresh(p)
    return p

@router.get("", response_model=list[schemas.PickOut])
def list_picks(db: Session = Depends(get_db)):
    return db.query(models.Pick).order_by(models.Pick.overall_no.asc()).all()

@router.delete("/{pick_id}")
def delete_pick(pick_id: int, db: Session = Depends(get_db)):
    p = db.query(models.Pick).filter_by(pick_id=pick_id).first()
    if not p: raise HTTPException(status_code=404, detail="pick not found")
    db.delete(p); db.commit()
    return {"ok": True, "deleted_pick_id": pick_id}
