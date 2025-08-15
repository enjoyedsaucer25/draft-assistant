from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..db import get_db
from .. import models

router = APIRouter(prefix="/edits", tags=["edits"])

@router.post("/tier/{player_id}")
def set_tier_override(
    player_id: str,
    tier: str | None = Query(None, description="Set integer tier, or empty/null to clear"),
    db: Session = Depends(get_db),
):
    """
    Set or clear a tier override for a player.

    - tier omitted / empty string / 'null' -> remove override
    - otherwise must be an int
    """
    p = db.query(models.Player).filter_by(player_id=player_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="player not found")

    # Normalize "clear" cases
    if tier is None or tier == "" or (isinstance(tier, str) and tier.lower() == "null"):
        row = db.query(models.TierOverride).filter_by(player_id=player_id).first()
        if row:
            db.delete(row)
            db.commit()
        return {"ok": True, "tier_override": None}

    # Parse to int
    try:
        tval = int(tier)
    except Exception:
        raise HTTPException(status_code=400, detail="tier must be an integer or empty to clear")

    row = db.query(models.TierOverride).filter_by(player_id=player_id).first()
    if not row:
        row = models.TierOverride(player_id=player_id, tier_override=tval)
        db.add(row)
    else:
        row.tier_override = tval
    db.commit()
    return {"ok": True, "tier_override": row.tier_override}


@router.post("/notes")
def add_note(
    player_id: str,
    text: str,
    team_slot_id: int | None = None,
    db: Session = Depends(get_db)
):
    p = db.query(models.Player).filter_by(player_id=player_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="player not found")
    n = models.Note(player_id=player_id, text=text, team_slot_id=team_slot_id)
    db.add(n)
    db.commit()
    db.refresh(n)
    return {"ok": True, "note_id": n.note_id}


@router.get("/notes")
def list_notes(
    player_id: str | None = None,
    team_slot_id: int | None = None,
    db: Session = Depends(get_db)
):
    q = db.query(models.Note)
    if player_id:
        q = q.filter_by(player_id=player_id)
    if team_slot_id is not None:
        q = q.filter_by(team_slot_id=team_slot_id)
    return [
        {
            "note_id": n.note_id,
            "player_id": n.player_id,
            "team_slot_id": n.team_slot_id,
            "text": n.text,
            "ts": n.ts,
        }
        for n in q.order_by(models.Note.ts.desc()).all()
    ]
