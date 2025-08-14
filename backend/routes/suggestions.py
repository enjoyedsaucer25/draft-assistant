from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..db import get_db
from .. import models, schemas

router = APIRouter(prefix="/suggestions", tags=["suggestions"])

@router.get("", response_model=schemas.SuggestionOut)
def suggestions(
    limit_top: int = Query(3, ge=1, le=10),
    limit_next: int = Query(10, ge=1, le=30),
    position: str | None = Query(None),
    db: Session = Depends(get_db)
):
    picked_ids = [pid for (pid,) in db.query(models.Pick.player_id).all()]
    q = db.query(models.Player, models.ConsensusRank).join(
        models.ConsensusRank,
        (models.ConsensusRank.player_id == models.Player.player_id)
        & (models.ConsensusRank.season == models.Player.season)
    )
    if position:
        q = q.filter(models.Player.position == position)
    if picked_ids:
        q = q.filter(~models.Player.player_id.in_(picked_ids))
    rows = q.order_by(
        (models.ConsensusRank.ecr_rank.is_(None)).asc(),
        models.ConsensusRank.ecr_rank.asc()
    ).limit(limit_top + limit_next).all()
    players = [r[0] for r in rows]
    return {"top": players[:limit_top], "next": players[limit_top:]}
