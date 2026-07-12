from sqlalchemy import Column, Integer, Float, String, Boolean, ForeignKey, DateTime, JSON, Text
from sqlalchemy.orm import relationship
from .database import Base
import datetime

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_admin = Column(Boolean, default=False)
    seat_id = Column(String, nullable=True) # Mapping Poste 2D
    team_name = Column(String, nullable=True) # Nom d'équipe
    ia_blocked = Column(Boolean, default=False) # Admin can block user from AI chat
    points = Column(Float, default=0) # Accumulated tournament points
    avatar_url = Column(String, nullable=True) # URL / path of user avatar
    avatar_shape = Column(String, default="circle") # Display shape: circle, rounded, square
    last_active_at = Column(DateTime, nullable=True)
    
    @property
    def is_online(self) -> bool:
        from .database import ACTIVE_USERS
        last_active = ACTIVE_USERS.get(self.id)
        if not last_active:
            return False
        import datetime
        return (datetime.datetime.utcnow() - last_active).total_seconds() < 120
    
    tournaments = relationship("TournamentParticipant", back_populates="user")

class Game(Base):
    __tablename__ = "games"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    image_url = Column(String, nullable=True)
    rules = Column(Text, nullable=True)
    default_config = Column(JSON, nullable=True) # e.g. team_size, bracket_type
    
    tournaments = relationship("Tournament", back_populates="game", cascade="all, delete-orphan")

class Tournament(Base):
    __tablename__ = "tournaments"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    status = Column(String, default="OPEN") # OPEN, RUNNING, DONE, CLOSED
    game_id = Column(Integer, ForeignKey("games.id", ondelete="CASCADE"))
    config = Column(JSON, nullable=True) # Settings: bracket_type, use_teams, pts_*, etc.
    bracket = Column(JSON, nullable=True) # Match data after start
    results = Column(JSON, nullable=True) # Final standings + points distributed at close
    points_per_win = Column(Integer, default=3)
    
    game = relationship("Game", back_populates="tournaments")
    participants = relationship("TournamentParticipant", back_populates="tournament", cascade="all, delete-orphan")
    teams = relationship("TournamentTeam", back_populates="tournament", cascade="all, delete-orphan")


class TournamentParticipant(Base):
    __tablename__ = "tournament_participants"
    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    team_name = Column(String, nullable=True)
    
    tournament = relationship("Tournament", back_populates="participants")
    user = relationship("User", back_populates="tournaments")

class TournamentTeam(Base):
    __tablename__ = "tournament_teams"
    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id", ondelete="CASCADE"))
    name = Column(String)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    tournament = relationship("Tournament", back_populates="teams")
    members = relationship("TournamentTeamMember", back_populates="team", cascade="all, delete-orphan")

class TournamentTeamMember(Base):
    __tablename__ = "tournament_team_members"
    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("tournament_teams.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    
    team = relationship("TournamentTeam", back_populates="members")

class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text)
    metadata_json = Column(JSON) # e.g. game_id, category
    # Embedding stored as JSON-serialized list of floats (searched via numpy in memory)
    embedding_json = Column(Text, nullable=True)

class RoomMap(Base):
    __tablename__ = "room_map"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, default="Main Room")
    layout = Column(JSON) # SVG coordinates, background image URL, etc.

class MatchReport(Base):
    __tablename__ = "match_reports"
    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id", ondelete="CASCADE"))
    match_s = Column(Integer) # Bracket section
    match_r = Column(Integer) # Round
    match_m = Column(Integer) # Match index
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    score = Column(JSON) # [score_p1, score_p2]
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class Conflict(Base):
    __tablename__ = "conflicts"
    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id", ondelete="CASCADE"))
    match_id_str = Column(String) # e.g. "WB R1 M1"
    resolved = Column(Boolean, default=False)
    admin_notes = Column(Text, nullable=True)

class SystemConfig(Base):
    __tablename__ = "system_config"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True)
    value = Column(JSON) # Store any structured config

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    title = Column(String, default="Nouvelle conversation")
    model = Column(String, nullable=True) # Specific model for this conversation
    summary = Column(Text, nullable=True) # Intelligent context persistence
    
    compressed_context = Column(Text, nullable=True)
    compressed_at = Column(DateTime, nullable=True)
    compression_mode = Column(String, nullable=True)
    auto_compression_mode = Column(String, nullable=True)
    admin_override = Column(Boolean, default=False)  # When True, admin controls responses
    admin_last_read_message_id = Column(Integer, default=0)
    player_last_read_message_id = Column(Integer, default=0)
    title_generation_attempted = Column(Boolean, default=False, server_default="0")

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    messages = relationship("ChatMessage", back_populates="conversation", cascade="all, delete-orphan")

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"))
    role = Column(String) # user, bot
    content = Column(Text)
    image_path = Column(String, nullable=True)  # Relative path to attached image
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    meta = Column(JSON, nullable=True)
    
    conversation = relationship("Conversation", back_populates="messages")

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    type = Column(String)  # "tournament_closed", "admin_message", "system"
    title = Column(String)
    content = Column(Text)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    metadata_json = Column(JSON, nullable=True)  # tournament_id, conversation_id, etc.

class PrivateMessage(Base):
    __tablename__ = "private_messages"
    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    receiver_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    content = Column(Text)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class GroupChannel(Base):
    """Canal de groupe (team-only ou inter-team). AXE-12."""
    __tablename__ = "group_channels"
    id = Column(Integer, primary_key=True, index=True)
    channel_key = Column(String, unique=True, index=True)  # "team:Alpha Wolves" ou "inter:Alpha Wolves|Neon Vipers"
    channel_type = Column(String)  # "team" ou "inter"
    team_names = Column(JSON)  # ["Alpha Wolves"] ou ["Alpha Wolves", "Neon Vipers"]
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    messages = relationship("GroupMessage", back_populates="channel", cascade="all, delete-orphan")

class GroupMessage(Base):
    """Message dans un canal de groupe. AXE-12."""
    __tablename__ = "group_messages"
    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(Integer, ForeignKey("group_channels.id", ondelete="CASCADE"))
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    channel = relationship("GroupChannel", back_populates="messages")

class GroupMessageRead(Base):
    """Dernier message lu par user dans un channel. AXE-12."""
    __tablename__ = "group_message_reads"
    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(Integer, ForeignKey("group_channels.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    last_read_message_id = Column(Integer, default=0)

class Award(Base):
    """Prix loufoques et classiques de fin de LAN."""
    __tablename__ = "awards"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    award_key = Column(String, nullable=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", backref="awards")

class AdminCallRequest(Base):
    """Demandes d'escalade vers un admin déclenchées par l'IA ou manuellement."""
    __tablename__ = "admin_call_requests"
    id               = Column(Integer, primary_key=True, index=True)
    user_id          = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    conversation_id  = Column(Integer, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    reason           = Column(Text)           # Explication concise du problème
    question         = Column(Text)           # Reformulation structurée de la demande non résolue
    source           = Column(String, default="manual")  # "manual" | "ia"
    status           = Column(String, default="pending")  # pending / resolved / dismissed
    created_at       = Column(DateTime, default=datetime.datetime.utcnow)
    resolved_at      = Column(DateTime, nullable=True)
    resolved_by      = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolution_note  = Column(Text, nullable=True)

class RagSuggestion(Base):
    """Suggestions de contenu RAG générées par l'IA en cas de lacune de connaissance."""
    __tablename__ = "rag_suggestions"
    id               = Column(Integer, primary_key=True, index=True)
    user_id          = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    conversation_id  = Column(Integer, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    question         = Column(Text)           # Question structurée générée par l'IA
    context          = Column(Text)           # Ce que l'utilisateur a demandé (texte brut)
    category         = Column(String, nullable=True)  # technique / règles / logistique / autre
    similarity_hash  = Column(String, nullable=True, index=True)  # MD5 normalisé pour dédoublonnage
    status           = Column(String, default="pending")  # pending / approved / rejected
    created_at       = Column(DateTime, default=datetime.datetime.utcnow)
    approved_at      = Column(DateTime, nullable=True)
    approved_by      = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_content = Column(Text, nullable=True)   # Réponse admin avant injection RAG

