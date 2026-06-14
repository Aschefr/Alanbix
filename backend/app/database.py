import os
import sqlite3
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# SQLite database — stored in persistent volume
DB_PATH = os.getenv("DATABASE_PATH", "/app/data/alanbix.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False
)

# Enable WAL mode for concurrent read/write safety
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
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
        _safe_add_column(conn, "tournaments", "points_per_win", "INTEGER DEFAULT 3")
        _safe_add_column(conn, "tournaments", "bracket", "JSON")
        _safe_add_column(conn, "tournament_teams", "created_by", "INTEGER")
        _safe_add_column(conn, "awards", "award_key", "VARCHAR")
        _safe_add_column(conn, "conversations", "admin_last_read_message_id", "INTEGER DEFAULT 0")
        _safe_add_column(conn, "conversations", "player_last_read_message_id", "INTEGER DEFAULT 0")
        
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
