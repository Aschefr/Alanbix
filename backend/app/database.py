import os
import sqlite3
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# SQLite database — stored in persistent volume
DB_PATH = os.getenv("DATABASE_PATH", "/app/data/alanbix.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Global in-memory presence tracking to prevent writing locks on SQLite
ACTIVE_USERS = {}  # user_id -> datetime.datetime


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False
)

# Disable WAL mode on Windows Docker mounts due to mmap/shared-memory limitations on host mounts
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=DELETE")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def init_db():
    # Import models to register them
    from . import models
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    # Run safe migrations (ADD COLUMN only — SQLite limitation)
    with engine.connect() as conn:
        # Sentinel Chat Migrations
        _safe_add_column(conn, "conversations", "compressed_context", "TEXT")
        _safe_add_column(conn, "conversations", "compressed_at", "TIMESTAMP")
        _safe_add_column(conn, "conversations", "compression_mode", "VARCHAR")
        _safe_add_column(conn, "conversations", "auto_compression_mode", "VARCHAR")
        _safe_add_column(conn, "conversations", "admin_override", "BOOLEAN DEFAULT 0")
        _safe_add_column(conn, "chat_messages", "image_path", "VARCHAR")
        _safe_add_column(conn, "chat_messages", "meta", "JSON")
        _safe_add_column(conn, "users", "team_name", "VARCHAR")
        _safe_add_column(conn, "users", "ia_blocked", "BOOLEAN DEFAULT 0")
        _safe_add_column(conn, "users", "avatar_url", "VARCHAR")
        _safe_add_column(conn, "users", "avatar_shape", "VARCHAR DEFAULT 'circle'")
        _safe_add_column(conn, "users", "last_active_at", "TIMESTAMP")
        _safe_add_column(conn, "tournaments", "points_per_win", "INTEGER DEFAULT 3")
        _safe_add_column(conn, "tournaments", "bracket", "JSON")
        _safe_add_column(conn, "tournament_teams", "created_by", "INTEGER")
        _safe_add_column(conn, "awards", "award_key", "VARCHAR")
        _safe_add_column(conn, "conversations", "admin_last_read_message_id", "INTEGER DEFAULT 0")
        _safe_add_column(conn, "conversations", "player_last_read_message_id", "INTEGER DEFAULT 0")
        _safe_add_column(conn, "conversations", "title_generation_attempted", "BOOLEAN DEFAULT 0")
        _safe_add_column(conn, "users", "public_chat_muted_until", "TIMESTAMP")
        _safe_add_column(conn, "public_chat_messages", "reactions", "JSON")
        _safe_add_column(conn, "public_chat_messages", "reply_to_id", "INTEGER")

        # Create critical performance indexes if they don't exist
        indexes = [
            ("ix_tournaments_game_id", "tournaments", "game_id"),
            ("ix_tournaments_status", "tournaments", "status"),
            ("ix_tournament_participants_tournament_id", "tournament_participants", "tournament_id"),
            ("ix_tournament_participants_user_id", "tournament_participants", "user_id"),
            ("ix_tournament_teams_tournament_id", "tournament_teams", "tournament_id"),
            ("ix_tournament_teams_created_by", "tournament_teams", "created_by"),
            ("ix_tournament_team_members_team_id", "tournament_team_members", "team_id"),
            ("ix_tournament_team_members_user_id", "tournament_team_members", "user_id"),
            ("ix_match_reports_tournament_id", "match_reports", "tournament_id"),
            ("ix_match_reports_user_id", "match_reports", "user_id"),
            ("ix_conflicts_tournament_id", "conflicts", "tournament_id"),
            ("ix_conversations_user_id", "conversations", "user_id"),
            ("ix_conversations_created_at", "conversations", "created_at"),
            ("ix_chat_messages_conversation_id", "chat_messages", "conversation_id"),
            ("ix_chat_messages_timestamp", "chat_messages", "timestamp"),
            ("ix_notifications_user_id", "notifications", "user_id"),
            ("ix_notifications_is_read", "notifications", "is_read"),
            ("ix_notifications_created_at", "notifications", "created_at"),
            ("ix_private_messages_sender_id", "private_messages", "sender_id"),
            ("ix_private_messages_receiver_id", "private_messages", "receiver_id"),
            ("ix_private_messages_created_at", "private_messages", "created_at"),
            ("ix_group_messages_channel_id", "group_messages", "channel_id"),
            ("ix_group_messages_created_at", "group_messages", "created_at"),
            ("ix_group_message_reads_channel_id", "group_message_reads", "channel_id"),
            ("ix_group_message_reads_user_id", "group_message_reads", "user_id"),
            ("ix_awards_user_id", "awards", "user_id"),
            ("ix_admin_call_requests_user_id", "admin_call_requests", "user_id"),
            ("ix_admin_call_requests_conversation_id", "admin_call_requests", "conversation_id"),
            ("ix_admin_call_requests_status", "admin_call_requests", "status"),
            ("ix_rag_suggestions_user_id", "rag_suggestions", "user_id"),
            ("ix_rag_suggestions_conversation_id", "rag_suggestions", "conversation_id"),
            ("ix_rag_suggestions_status", "rag_suggestions", "status"),
            ("ix_public_chat_messages_user_id", "public_chat_messages", "user_id"),
            ("ix_public_chat_messages_reply_to_id", "public_chat_messages", "reply_to_id"),
            ("ix_public_chat_messages_created_at", "public_chat_messages", "created_at"),
            ("ix_public_chat_messages_is_deleted", "public_chat_messages", "is_deleted"),
        ]
        for idx_name, table_name, col_name in indexes:
            try:
                conn.execute(__import__('sqlalchemy').text(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table_name} ({col_name})"
                ))
            except Exception:
                pass

        # Purge any orphan/legacy tournaments with NULL game_id or missing games (due to previous SQLAlchemy missing cascade behavior)
        conn.execute(__import__('sqlalchemy').text("DELETE FROM tournaments WHERE game_id IS NULL OR game_id NOT IN (SELECT id FROM games)"))
        conn.commit()

def _safe_add_column(conn, table, column, col_type):
    """SQLite-safe ADD COLUMN — skips silently if column exists."""
    try:
        conn.execute(
            __import__('sqlalchemy').text(
                f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
            )
        )
    except Exception:
        pass  # Column already exists

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
