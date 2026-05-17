from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Any
from datetime import datetime

class UserBase(BaseModel):
    username: str

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int
    is_admin: bool
    ia_blocked: Optional[bool] = False
    seat_id: Optional[str] = None
    team_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class GameBase(BaseModel):
    name: str
    image_url: Optional[str] = None
    rules: Optional[str] = None
    default_config: Optional[dict] = None

class GameCreate(GameBase):
    pass

class GameUpdate(BaseModel):
    name: Optional[str] = None
    image_url: Optional[str] = None
    rules: Optional[str] = None
    default_config: Optional[dict] = None

class Game(GameBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class TournamentBase(BaseModel):
    name: Optional[str] = None
    game_id: Optional[int] = None
    config: Optional[Any] = None
    bracket: Optional[Any] = None
    points_per_win: Optional[int] = 3

class TournamentCreate(TournamentBase):
    pass

class TournamentUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    config: Optional[Any] = None
    bracket: Optional[Any] = None
    points_per_win: Optional[int] = None

class TournamentParticipant(BaseModel):
    id: int
    user_id: int
    team_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class Tournament(TournamentBase):
    id: int
    status: str
    points_per_win: Optional[int] = 3
    participants: List[TournamentParticipant] = []
    model_config = ConfigDict(from_attributes=True)


# AI Chat Schemas
class ChatMessageBase(BaseModel):
    role: str
    content: str

class ChatMessage(ChatMessageBase):
    id: int
    timestamp: datetime
    model_config = ConfigDict(from_attributes=True)

class ConversationBase(BaseModel):
    title: str

class Conversation(ConversationBase):
    id: int
    user_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
