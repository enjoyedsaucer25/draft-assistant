from pydantic import BaseModel
from typing import Optional
class PlayerOut(BaseModel):
    player_id: str
    season: int
    clean_name: str
    position: str
    team: Optional[str] = None
    bye_week: Optional[int] = None
    class Config: from_attributes = True
