# backend/models.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Boolean,
)
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class Player(Base):
    __tablename__ = "players"

    player_id: Mapped[str] = mapped_column(String, primary_key=True)
    season: Mapped[int] = mapped_column(Integer, nullable=False, default=2025)
    clean_name: Mapped[str] = mapped_column(String, index=True, nullable=False)
    position: Mapped[str] = mapped_column(String, index=True, nullable=False)
    team: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    bye_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # External IDs (optional)
    sleeper_id: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    fp_id: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    espn_id: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    nfl_id: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)


class ConsensusRank(Base):
    __tablename__ = "consensus_ranks"

    season: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[str] = mapped_column(
        String, ForeignKey("players.player_id"), primary_key=True
    )
    ecr_rank: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ecr_pos_rank: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tier: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String, default="fantasypros")
    asof_ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TeamLeague(Base):
    __tablename__ = "teams_league"

    team_slot_id: Mapped[int] = mapped_column(Integer, primary_key=True)  # 1..12
    team_name: Mapped[str] = mapped_column(String, nullable=False)
    draft_position: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..12
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Pick(Base):
    __tablename__ = "picks"

    pick_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    round_no: Mapped[int] = mapped_column(Integer, nullable=False)
    overall_no: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    team_slot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams_league.team_slot_id"), nullable=False, index=True
    )
    player_id: Mapped[str] = mapped_column(
        String, ForeignKey("players.player_id"), nullable=False, index=True
    )
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("overall_no", name="uq_overall_no"),
        UniqueConstraint("player_id", name="uq_picked_player"),
    )


class Source(Base):
    __tablename__ = "sources"

    source_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)  # 'sleeper','fantasypros','cbs'
    kind: Mapped[Optional[str]] = mapped_column(String, nullable=True)      # 'players','ecr','adp','injuries','projections'


class ImportRun(Base):
    __tablename__ = "import_runs"

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("sources.source_id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ADP(Base):
    __tablename__ = "adp"

    season: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[str] = mapped_column(
        String, ForeignKey("players.player_id"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String, primary_key=True)  # 'fp_composite','espn', etc
    adp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rank: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sample_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    asof_ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Projection(Base):
    __tablename__ = "projections"

    season: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[str] = mapped_column(
        String, ForeignKey("players.player_id"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String, primary_key=True)   # 'fp','fantasysharks', etc

    projected_points: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pass_yd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pass_td: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pass_int: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rush_yd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rush_td: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rec_rec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rec_yd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rec_td: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    xp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    asof_ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Injury(Base):
    __tablename__ = "injuries"

    season: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[str] = mapped_column(
        String, ForeignKey("players.player_id"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String, primary_key=True)   # 'cbs'
    status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    body_part: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    practice_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    return_timeline: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    asof_ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TierOverride(Base):
    __tablename__ = "tier_overrides"

    player_id: Mapped[str] = mapped_column(
        String, ForeignKey("players.player_id"), primary_key=True
    )
    tier_override: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Note(Base):
    __tablename__ = "notes"

    note_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(
        String, ForeignKey("players.player_id"), index=True, nullable=False
    )
    team_slot_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("teams_league.team_slot_id"), nullable=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
