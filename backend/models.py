from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, UniqueConstraint
from datetime import datetime
from .db import Base
from sqlalchemy.orm import relationship
from datetime import datetime

class Player(Base):
    __tablename__ = "players"
    player_id = Column(String, primary_key=True)
    season = Column(Integer, nullable=False, default=2025)
    clean_name = Column(String, index=True, nullable=False)
    position = Column(String, index=True, nullable=False)
    team = Column(String, index=True)
    bye_week = Column(Integer)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    )