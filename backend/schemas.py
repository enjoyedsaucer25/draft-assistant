# backend/schemas.py
from __future__ import annotations
from typing import Optional, Literal, List
from pydantic import BaseModel


class PlayerOut(BaseModel):
    player_id: str
    season: int
    clean_name: str
    position: str
    team: Optional[str] = None
    bye_week: Optional[int] = None
    class Config: from_attributes = True


class TeamIn(BaseModel):
    team_slot_id: int
    team_name: str
    draft_position: int


class TeamOut(TeamIn):
    class Config: from_attributes = True


class PickIn(BaseModel):
    round_no: int
    overall_no: int
    team_slot_id: int
    player_id: str


class PickOut(PickIn):
    pick_id: int
    class Config: from_attributes = True


class EnrichedPlayerOut(BaseModel):
    player_id: str
    name: str
    pos: str
    team: Optional[str] = None
    ecr: Optional[float] = None
    ecr_pos: Optional[float] = None
    tier: Optional[int] = None
    tier_source: Literal["core", "override"] = "core"
    adp: Optional[float] = None
    injury_status: Optional[str] = None
    injury_body: Optional[str] = None
    proj_pts: Optional[float] = None  # NEW


class SuggestionOut(BaseModel):
    top: List[PlayerOut]
    next: List[PlayerOut]
