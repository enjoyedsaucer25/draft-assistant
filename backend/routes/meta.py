from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, and_, case, literal
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models
from ..schemas import EnrichedPlayerOut

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/players_enriched", response_model=List[EnrichedPlayerOut])
def players_enriched(
    season: int = Query(..., description="Season to return"),
    position: Optional[str] = Query(None, description="QB/RB/WR/TE/K/DEF"),
    q: Optional[str] = Query(None, description="Name/Team search"),
    limit: int = Query(300, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    # Base players
    p = db.query(models.Player).filter(models.Player.season == season)
    if position:
        p = p.filter(models.Player.position == position)
    if q:
        like = f"%{q}%"
        p = p.filter(
            (models.Player.clean_name.ilike(like))
            | (models.Player.team.ilike(like))
            | (models.Player.position.ilike(like))
        )
    players_sub = p.subquery()

    # Latest consensus rank
    cr_max = (
        db.query(
            models.ConsensusRank.player_id.label("player_id"),
            func.max(models.ConsensusRank.asof_ts).label("max_ts"),
        )
        .filter(models.ConsensusRank.season == season)
        .group_by(models.ConsensusRank.player_id)
        .subquery()
    )
    cr_latest = (
        db.query(
            models.ConsensusRank.player_id,
            models.ConsensusRank.ecr_rank,
            models.ConsensusRank.ecr_pos_rank,
            models.ConsensusRank.tier,
        )
        .join(
            cr_max,
            and_(
                models.ConsensusRank.player_id == cr_max.c.player_id,
                models.ConsensusRank.asof_ts == cr_max.c.max_ts,
            ),
        )
        .subquery()
    )

    # Latest ADP
    adp_max = (
        db.query(
            models.ADP.player_id.label("player_id"),
            func.max(models.ADP.asof_ts).label("max_ts"),
        )
        .filter(models.ADP.season == season)
        .group_by(models.ADP.player_id)
        .subquery()
    )
    adp_latest = (
        db.query(
            models.ADP.player_id,
            models.ADP.adp,
        )
        .join(
            adp_max,
            and_(
                models.ADP.player_id == adp_max.c.player_id,
                models.ADP.asof_ts == adp_max.c.max_ts,
            ),
        )
        .subquery()
    )

    # Latest injuries
    inj_max = (
        db.query(
            models.Injury.player_id.label("player_id"),
            func.max(models.Injury.asof_ts).label("max_ts"),
        )
        .filter(models.Injury.season == season)
        .group_by(models.Injury.player_id)
        .subquery()
    )
    inj_latest = (
        db.query(
            models.Injury.player_id,
            models.Injury.status,
            models.Injury.body,
        )
        .join(
            inj_max,
            and_(
                models.Injury.player_id == inj_max.c.player_id,
                models.Injury.asof_ts == inj_max.c.max_ts,
            ),
        )
        .subquery()
    )

    # Latest projections (include components)
    proj_max = (
        db.query(
            models.Projection.player_id.label("player_id"),
            func.max(models.Projection.asof_ts).label("max_ts"),
        )
        .filter(models.Projection.season == season)
        .group_by(models.Projection.player_id)
        .subquery()
    )
    proj_latest = (
        db.query(
            models.Projection.player_id,
            models.Projection.pts,
            models.Projection.pass_yd,
            models.Projection.pass_td,
            models.Projection.rush_yd,
            models.Projection.rush_td,
            models.Projection.rec,
            models.Projection.rec_yd,
            models.Projection.rec_td,
        )
        .join(
            proj_max,
            and_(
                models.Projection.player_id == proj_max.c.player_id,
                models.Projection.asof_ts == proj_max.c.max_ts,
            ),
        )
        .subquery()
    )

    # Thousands fix in SQL: pass_yd & rec_yd only
    pass_yd_fixed = case(
        (proj_latest.c.pass_yd.isnot(None), case(
            (proj_latest.c.pass_yd < 50, proj_latest.c.pass_yd * 1000.0),
            else_=proj_latest.c.pass_yd
        )),
        else_=None
    )
    rec_yd_fixed = case(
        (proj_latest.c.rec_yd.isnot(None), case(
            (proj_latest.c.rec_yd < 50, proj_latest.c.rec_yd * 1000.0),
            else_=proj_latest.c.rec_yd
        )),
        else_=None
    )

    # Half-PPR calc if pts is NULL (do NOT multiply rush_yd)
    computed_pts = func.coalesce(
        proj_latest.c.pts,
        (
            func.coalesce(0.04 * pass_yd_fixed, 0.0)
            + func.coalesce(4.0 * proj_latest.c.pass_td, 0.0)
            + func.coalesce(0.1 * proj_latest.c.rush_yd, 0.0)
            + func.coalesce(6.0 * proj_latest.c.rush_td, 0.0)
            + func.coalesce(0.5 * proj_latest.c.rec, 0.0)
            + func.coalesce(0.1 * rec_yd_fixed, 0.0)
            + func.coalesce(6.0 * proj_latest.c.rec_td, 0.0)
        )
    )

    rows = (
        db.query(
            players_sub.c.player_id,
            players_sub.c.clean_name,
            players_sub.c.position,
            players_sub.c.team,
            cr_latest.c.ecr_rank,
            cr_latest.c.ecr_pos_rank,
            cr_latest.c.tier,
            adp_latest.c.adp,
            inj_latest.c.status,
            inj_latest.c.body,
            computed_pts.label("proj_pts"),
            literal(None).label("tier_override"),
        )
        .outerjoin(cr_latest, cr_latest.c.player_id == players_sub.c.player_id)
        .outerjoin(adp_latest, adp_latest.c.player_id == players_sub.c.player_id)
        .outerjoin(inj_latest, inj_latest.c.player_id == players_sub.c.player_id)
        .outerjoin(proj_latest, proj_latest.c.player_id == players_sub.c.player_id)
        .order_by(
            func.coalesce(cr_latest.c.ecr_rank, 1e9).asc(),
            players_sub.c.clean_name.asc(),
        )
        .limit(limit)
        .all()
    )

    out: List[EnrichedPlayerOut] = []
    for r in rows:
        out.append(
            EnrichedPlayerOut(
                player_id=r.player_id,
                name=r.clean_name,
                pos=r.position,
                team=r.team,
                ecr=r.ecr_rank,
                ecr_pos=r.ecr_pos_rank,
                tier=r.tier,
                tier_source="core",
                adp=r.adp,
                injury_status=r.status,
                injury_body=r.body,
                proj_pts=float(r.proj_pts) if r.proj_pts is not None else None,
            )
        )
    return out
