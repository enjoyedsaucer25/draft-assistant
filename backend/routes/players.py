from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..db import get_db
from .. import models, schemas

router = APIRouter(prefix="/players", tags=["players"])

@router.get("", response_model=list[schemas.PlayerOut])
def list_players(
    q: str | None = Query(None, description="search by name/position/team"),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    qry = db.query(models.Player)
    if q:
        like = f"%{q}%"
        qry = qry.filter(
            (models.Player.clean_name.ilike(like)) |
            (models.Player.position.ilike(like)) |
            (models.Player.team.ilike(like))
        )
    return qry.order_by(models.Player.clean_name.asc()).limit(limit).all()
