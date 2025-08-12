from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
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

class ConsensusRank(Base):
    __tablename__ = "consensus_ranks"
    season = Column(Integer, primary_key=True)
    player_id = Column(String, ForeignKey("players.player_id"), primary_key=True)
    ecr_rank = Column(Float)
    ecr_pos_rank = Column(Float)
    tier = Column(Integer)
    source = Column(String, default="fantasypros")
    asof_ts = Column(DateTime, default=datetime.utcnow)
