from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, UniqueConstraint, Boolean, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from .db import Base

class Player(Base):
    __tablename__ = "players"
    player_id = Column(String, primary_key=True)
    season = Column(Integer, nullable=False, default=2025)
    clean_name = Column(String, index=True, nullable=False)
    position = Column(String, index=True, nullable=False)
    team = Column(String, index=True)
    bye_week = Column(Integer)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    sleeper_id = Column(String, index=True, nullable=True)
    fp_id = Column(String, index=True, nullable=True)     # FantasyPros id if you later parse it
    espn_id = Column(String, index=True, nullable=True)
    nfl_id = Column(String, index=True, nullable=True)

class ConsensusRank(Base):
    __tablename__ = "consensus_ranks"
    season = Column(Integer, primary_key=True)
    player_id = Column(String, ForeignKey("players.player_id"), primary_key=True)
    ecr_rank = Column(Float)
    ecr_pos_rank = Column(Float)
    tier = Column(Integer)
    source = Column(String, default="fantasypros")
    asof_ts = Column(DateTime, default=datetime.utcnow)
    
class TeamLeague(Base):
    __tablename__ = "teams_league"
    team_slot_id = Column(Integer, primary_key=True)  # 1..12
    team_name = Column(String, nullable=False)
    draft_position = Column(Integer, nullable=False)  # 1..12 for snake order
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Pick(Base):
    __tablename__ = "picks"
    pick_id = Column(Integer, primary_key=True, autoincrement=True)
    round_no = Column(Integer, nullable=False)
    overall_no = Column(Integer, nullable=False, index=True)
    team_slot_id = Column(Integer, ForeignKey("teams_league.team_slot_id"), nullable=False, index=True)
    player_id = Column(String, ForeignKey("players.player_id"), nullable=False, index=True)
    ts = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("overall_no", name="uq_overall_no"),
        UniqueConstraint("player_id", name="uq_picked_player"),
    )

class Source(Base):
    __tablename__ = "sources"
    source_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)   # 'sleeper','fantasypros','cbs'
    kind = Column(String, nullable=True)                 # 'players','ecr','adp','injuries','projections'

class ImportRun(Base):
    __tablename__ = "import_runs"
    run_id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(Integer, ForeignKey("sources.source_id"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    success = Column(Boolean, default=False, nullable=False)
    row_count = Column(Integer, default=0, nullable=False)
    error_text = Column(Text, nullable=True)

class ADP(Base):
    __tablename__ = "adp"
    season = Column(Integer, primary_key=True)
    player_id = Column(String, ForeignKey("players.player_id"), primary_key=True)
    source = Column(String, primary_key=True)  # 'fp_composite','fp_sleepper','espn', etc
    adp = Column(Float)
    rank = Column(Float)
    sample_size = Column(Integer)
    asof_ts = Column(DateTime, default=datetime.utcnow)

class Projection(Base):
    __tablename__ = "projections"
    season = Column(Integer, primary_key=True)
    player_id = Column(String, ForeignKey("players.player_id"), primary_key=True)
    source = Column(String, primary_key=True)   # 'fp','fantasysharks', etc
    projected_points = Column(Float)
    pass_yd = Column(Float); pass_td = Column(Float); pass_int = Column(Float)
    rush_yd = Column(Float); rush_td = Column(Float)
    rec_rec = Column(Float); rec_yd = Column(Float); rec_td = Column(Float)
    fg = Column(Float); xp = Column(Float)
    asof_ts = Column(DateTime, default=datetime.utcnow)

class Injury(Base):
    __tablename__ = "injuries"
    season = Column(Integer, primary_key=True)
    player_id = Column(String, ForeignKey("players.player_id"), primary_key=True)
    source = Column(String, primary_key=True)   # 'cbs'
    status = Column(String)
    body_part = Column(String)
    practice_status = Column(String)
    probability = Column(Float)                 # if parseable
    return_timeline = Column(String)
    asof_ts = Column(DateTime, default=datetime.utcnow)

class TierOverride(Base):
    __tablename__ = "tier_overrides"
    player_id = Column(String, ForeignKey("players.player_id"), primary_key=True)
    tier_override = Column(Integer, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Note(Base):
    __tablename__ = "notes"
    note_id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(String, ForeignKey("players.player_id"), index=True, nullable=False)
    team_slot_id = Column(Integer, ForeignKey("teams_league.team_slot_id"), nullable=True)
    text = Column(Text, nullable=False)
    ts = Column(DateTime, default=datetime.utcnow, nullable=False)
