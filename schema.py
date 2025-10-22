from pydantic import BaseModel
from typing import Dict, List, Optional

class BookmakerOdds(BaseModel):
    back: Optional[float] = None
    lay: Optional[float] = None
    meta: Dict[str, str] = {}

class FancyLine(BaseModel):
    market: str
    yes: Optional[float] = None
    no: Optional[float] = None
    max_stake: Optional[str] = None
    extra: Dict[str, str] = {}

class SessionLine(BaseModel):
    label: str
    yes: Optional[float] = None
    no: Optional[float] = None
    extra: Dict[str, str] = {}

class MatchCard(BaseModel):
    match_id: str
    title: str
    teams: List[str] = []
    starts_at: Optional[str] = None
    status: str = "scheduled"  # scheduled|live|finished
    href: Optional[str] = None

class LiveMatchSnapshot(BaseModel):
    match_id: str
    bookmaker: Dict[str, BookmakerOdds] = {}
    fancy: List[FancyLine] = []
    sessions: List[SessionLine] = []
    result: Optional[str] = None

class LiveCricketPayload(BaseModel):
    fetched_at: str
    matches: List[MatchCard]
    live_details: Dict[str, LiveMatchSnapshot] = {}
