# backend/schemas.py
from __future__ import annotations
from typing import Optional, Literal

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


class TeamOut(BaseModel):
    team_slot_id: int
    team_name: str
    draft_position: int
    class Config: from_attributes = True


class PickIn(BaseModel):
    round_no: int
    overall_no: int
    team_slot_id: int
    player_id: str


class PickOut(BaseModel):
    pick_id: int
    round_no: int
    overall_no: int
    team_slot_id: int
    player_id: str
    class Config: from_attributes = True


class SuggestionOut(BaseModel):
    top: list[PlayerOut]
    next: list[PlayerOut]


class EnrichedPlayerOut(BaseModel):
    player_id: str
    name: str
    pos: str
    team: Optional[str] = None
    ecr: Optional[float] = None
    ecr_pos: Optional[float] = None
    tier: Optional[int] = None
    tier_source: Literal["core", "override"]
    adp: Optional[float] = None
    injury_status: Optional[str] = None
    injury_body: Optional[str] = None
