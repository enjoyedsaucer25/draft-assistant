# backend/routes/meta.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..db import get_db
from .. import models

router = APIRouter(prefix="/meta", tags=["meta"])

@router.get("/players_enriched")
def players_enriched(
    season: int = Query(...),
    position: str | None = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    # join players + consensus + adp (fp composite) + injuries + tier_override
    P, C, A, I, T = models.Player, models.ConsensusRank, models.ADP, models.Injury, models.TierOverride
    q = db.query(P, C.ecr_rank, C.ecr_pos_rank, C.tier, A.adp, I.status, I.body_part, T.tier_override)\
         .outerjoin(C, (C.player_id==P.player_id) & (C.season==season))\
         .outerjoin(A, (A.player_id==P.player_id) & (A.season==season) & (A.source=="fp_composite"))\
         .outerjoin(I, (I.player_id==P.player_id) & (I.season==season) & (I.source=="cbs"))\
         .outerjoin(T, (T.player_id==P.player_id))
    if position:
        q = q.filter(P.position==position)
    rows = q.order_by(C.ecr_rank.asc().nulls_last(), P.clean_name.asc()).limit(limit).all()
    out = []
    for (p, ecr, epos, tier, adp, istat, ibody, tovr) in rows:
        out.append({
            "player_id": p.player_id, "name": p.clean_name, "pos": p.position, "team": p.team,
            "ecr": ecr, "ecr_pos": epos, "tier": tovr if tovr is not None else tier,
            "tier_source": "override" if tovr is not None else "core",
            "adp": adp,
            "injury_status": istat, "injury_body": ibody,
        })
    return out
