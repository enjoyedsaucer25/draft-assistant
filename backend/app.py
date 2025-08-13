from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from .db import Base, engine, get_db
from . import models, schemas
from .ingest.csv_importer import import_from_csv
import os
from .config.settings import settings
from .routes import players, teams, picks, suggestions, admin

app = FastAPI(title="Draft Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

@app.get("/")
def home():
    return {"service": "Draft Assistant API", "ok": True, "hint": "see /health and /docs"}

@app.get("/health")
def health():
    return {"ok": True}

app.include_router(players.router)
app.include_router(teams.router)
app.include_router(picks.router)
app.include_router(suggestions.router)
app.include_router(admin.router)


@app.get("/players", response_model=list[schemas.PlayerOut])
def list_players(
    q: str | None = Query(None, description="search by name/position/team"),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
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

@app.post("/admin/import/csv")
def admin_import_csv(path: str, db: Session = Depends(get_db)):
    if not os.path.exists(path):
        raise HTTPException(status_code=400, detail=f"File not found: {path}")
    result = import_from_csv(path, db)
    if result["errors"]:
        raise HTTPException(status_code=400, detail=result)
    return {"ok": True, "result": result}

# --- Teams (setup & list) ---

@app.post("/teams/init", response_model=list[schemas.TeamOut])
def init_teams(db: Session = Depends(get_db)):
    """
    Quick initializer: creates 12 teams with default names and draft positions 1..12
    Safe to call multiple times; it will upsert names/positions if they exist.
    """
    created = []
    for i in range(1, 13):
        t = db.query(models.TeamLeague).filter_by(team_slot_id=i).first()
        if not t:
            t = models.TeamLeague(team_slot_id=i, team_name=f"Team {i}", draft_position=i)
            db.add(t)
        else:
            # keep existing, but ensure draft_position defaults to i if missing
            t.draft_position = t.draft_position or i
        created.append(t)
    db.commit()
    return created

@app.get("/teams", response_model=list[schemas.TeamOut])
def list_teams(db: Session = Depends(get_db)):
    return db.query(models.TeamLeague).order_by(models.TeamLeague.team_slot_id.asc()).all()

@app.post("/teams/upsert", response_model=schemas.TeamOut)
def upsert_team(payload: schemas.TeamIn, db: Session = Depends(get_db)):
    t = db.query(models.TeamLeague).filter_by(team_slot_id=payload.team_slot_id).first()
    if not t:
        t = models.TeamLeague(
            team_slot_id=payload.team_slot_id,
            team_name=payload.team_name,
            draft_position=payload.draft_position,
        )
        db.add(t)
    else:
        t.team_name = payload.team_name
        t.draft_position = payload.draft_position
    db.commit()
    db.refresh(t)
    return t

# --- Picks (create/list/delete -> undo) ---

@app.post("/picks", response_model=schemas.PickOut)
def create_pick(payload: schemas.PickIn, db: Session = Depends(get_db)):
    # sanity checks
    if not db.query(models.Player).filter_by(player_id=payload.player_id).first():
        raise HTTPException(status_code=400, detail="Unknown player_id")
    if not db.query(models.TeamLeague).filter_by(team_slot_id=payload.team_slot_id).first():
        raise HTTPException(status_code=400, detail="Unknown team_slot_id")
    # ensure overall unique
    exists = db.query(models.Pick).filter_by(overall_no=payload.overall_no).first()
    if exists:
        raise HTTPException(status_code=400, detail=f"overall_no {payload.overall_no} already used")

    p = models.Pick(
        round_no=payload.round_no,
        overall_no=payload.overall_no,
        team_slot_id=payload.team_slot_id,
        player_id=payload.player_id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p

@app.get("/picks", response_model=list[schemas.PickOut])
def list_picks(db: Session = Depends(get_db)):
    return db.query(models.Pick).order_by(models.Pick.overall_no.asc()).all()

@app.delete("/picks/{pick_id}")
def delete_pick(pick_id: int, db: Session = Depends(get_db)):
    p = db.query(models.Pick).filter_by(pick_id=pick_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="pick not found")
    db.delete(p)
    db.commit()
    return {"ok": True, "deleted_pick_id": pick_id}

# --- Suggestions (basic stub) ---

@app.get("/suggestions", response_model=schemas.SuggestionOut)
def suggestions(
    limit_top: int = Query(3, ge=1, le=10),
    limit_next: int = Query(10, ge=1, le=30),
    position: str | None = Query(None, description="Optional filter: QB/RB/WR/TE/K/DEF"),
    db: Session = Depends(get_db)
):
    """
    Very simple: use consensus ECR rank to suggest players, excluding already-picked.
    Later: blend weights, roster needs, tiers, run prediction, etc.
    """
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
    q = q.order_by(models.ConsensusRank.ecr_rank.asc().nulls_last())

    rows = q.limit(limit_top + limit_next).all()
    players = [r[0] for r in rows]
    top = players[:limit_top]
    nxt = players[limit_top:]
    return {"top": top, "next": nxt}

