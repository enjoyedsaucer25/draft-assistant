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
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


# ---------- Core domain ----------
class Player(Base):
    __tablename__ = "players"

    player_id: Mapped[str] = mapped_column(String, primary_key=True)
    season: Mapped[int] = mapped_column(Integer, index=True)
    clean_name: Mapped[str] = mapped_column(String, index=True)
    position: Mapped[str] = mapped_column(String, index=True)
    team: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    bye_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # external ids (optional)
    sleeper_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    espn_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    nfl_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    ranks: Mapped[list["ConsensusRank"]] = relationship(back_populates="player", cascade="all, delete-orphan")


class ConsensusRank(Base):
    __tablename__ = "consensus_ranks"
    __table_args__ = (
        UniqueConstraint("season", "player_id", "source", name="uq_consensus_source"),
        Index("ix_consensus_season_rank", "season", "ecr_rank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season: Mapped[int] = mapped_column(Integer, index=True)
    player_id: Mapped[str] = mapped_column(String, ForeignKey("players.player_id"), index=True)
    ecr_rank: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ecr_pos_rank: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tier: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String, default="fantasypros", index=True)
    asof_ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    player: Mapped["Player"] = relationship(back_populates="ranks")


class ADP(Base):
    __tablename__ = "adp"
    __table_args__ = (
        UniqueConstraint("season", "player_id", "source", name="uq_adp_source"),
        Index("ix_adp_season_adp", "season", "adp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season: Mapped[int] = mapped_column(Integer)
    player_id: Mapped[str] = mapped_column(String, ForeignKey("players.player_id"), index=True)
    source: Mapped[str] = mapped_column(String, default="fantasypros", index=True)
    adp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    adp_pos_rank: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sample_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    asof_ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Projection(Base):
    __tablename__ = "projections"
    __table_args__ = (UniqueConstraint("season", "player_id", "source", name="uq_proj_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season: Mapped[int] = mapped_column(Integer, index=True)
    player_id: Mapped[str] = mapped_column(String, ForeignKey("players.player_id"), index=True)
    source: Mapped[str] = mapped_column(String, default="fantasypros", index=True)
    pts: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Optional breakdowns if/when available
    pass_yd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pass_td: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rush_yd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rush_td: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rec_yd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rec_td: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    asof_ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Injury(Base):
    __tablename__ = "injuries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season: Mapped[int] = mapped_column(Integer, index=True)
    player_id: Mapped[str] = mapped_column(String, ForeignKey("players.player_id"), index=True)
    status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    body: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    asof_ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------- League and draft ----------
class TeamLeague(Base):
    __tablename__ = "teams_league"

    team_slot_id: Mapped[int] = mapped_column(Integer, primary_key=True)  # 1..12
    team_name: Mapped[str] = mapped_column(String)
    draft_position: Mapped[int] = mapped_column(Integer)  # 1..12


class Pick(Base):
    __tablename__ = "picks"

    pick_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    round_no: Mapped[int] = mapped_column(Integer, index=True)
    overall_no: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    team_slot_id: Mapped[int] = mapped_column(Integer, ForeignKey("teams_league.team_slot_id"))
    player_id: Mapped[str] = mapped_column(String, ForeignKey("players.player_id"))
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------- User board overrides & notes ----------
class UserBoardOverride(Base):
    __tablename__ = "user_board_overrides"
    __table_args__ = (UniqueConstraint("season", "player_id", name="uq_override_player"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season: Mapped[int] = mapped_column(Integer, index=True)
    player_id: Mapped[str] = mapped_column(String, ForeignKey("players.player_id"), index=True)
    tier_override: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rank_override: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    note_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    starred: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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


# ---------- Crosswalk ----------
class PlayerXWalk(Base):
    __tablename__ = "player_xwalk"
    __table_args__ = (UniqueConstraint("season", "source", "source_key", name="uq_xwalk_source_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season: Mapped[int] = mapped_column(Integer, index=True)
    source: Mapped[str] = mapped_column(String, index=True)   # "fantasypros"
    source_key: Mapped[str] = mapped_column(String, index=True)  # normalized "name|pos" (and team if present)
    player_id: Mapped[str] = mapped_column(String, ForeignKey("players.player_id"), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)


# ---------- Simple import bookkeeping ----------
class Source(Base):
    __tablename__ = "sources"

    source_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    kind: Mapped[str] = mapped_column(String)  # "players", "ecr", "adp", "projections", etc.


class ImportRun(Base):
    __tablename__ = "import_runs"

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("sources.source_id"))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    error_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
