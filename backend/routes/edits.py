from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from .. import models, schemas

router = APIRouter(prefix="/edits", tags=["edits"])

@router.post("/tier/{player_id}")
def set_tier_override(player_id: str, tier: int | None, db: Session = Depends(get_db)):
    p = db.query(models.Player).filter_by(player_id=player_id).first()
    if not p: raise HTTPException(404, "player not found")
    row = db.query(models.TierOverride).filter_by(player_id=player_id).first()
    if tier is None:
        if row:
            db.delete(row); db.commit()
        return {"ok": True, "tier_override": None}
    if not row:
        row = models.TierOverride(player_id=player_id, tier_override=tier)
        db.add(row)
    else:
        row.tier_override = tier
    db.commit()
    return {"ok": True, "tier_override": row.tier_override}

@router.post("/notes")
def add_note(player_id: str, text: str, team_slot_id: int | None = None, db: Session = Depends(get_db)):
    p = db.query(models.Player).filter_by(player_id=player_id).first()
    if not p: raise HTTPException(404, "player not found")
    n = models.Note(player_id=player_id, text=text, team_slot_id=team_slot_id)
    db.add(n); db.commit(); db.refresh(n)
    return {"ok": True, "note_id": n.note_id}

@router.get("/notes")
def list_notes(player_id: str | None = None, team_slot_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(models.Note)
    if player_id: q = q.filter_by(player_id=player_id)
    if team_slot_id is not None: q = q.filter_by(team_slot_id=team_slot_id)
    return [{"note_id": n.note_id, "player_id": n.player_id, "team_slot_id": n.team_slot_id, "text": n.text, "ts": n.ts} for n in q.order_by(models.Note.ts.desc()).all()]
