import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.auth import get_current_user, get_current_admin
from app import models, auth

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
PASS_HASH = auth.get_password_hash("pass")


@pytest.fixture()
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Seed 21 players (one shared hash: bcrypt is deliberately slow, ~0.25 s per call)
    for i in range(1, 22):
        user = models.User(username=f"Player{i}", hashed_password=PASS_HASH)
        db.add(user)

    admin = models.User(username="admin", is_admin=True, hashed_password=PASS_HASH)
    db.add(admin)
    db.commit()

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    def override_get_current_admin():
        return db_session.query(models.User).filter(models.User.username == "admin").first()

    def override_get_current_user():
        return db_session.query(models.User).filter(models.User.username == "admin").first()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_admin] = override_get_current_admin
    app.dependency_overrides[get_current_user] = override_get_current_user
    from app.auth import get_optional_user
    app.dependency_overrides[get_optional_user] = override_get_current_user

    # Mock IAQueueManager to avoid asyncio event loop conflicts across tests
    with patch("app.ia_queue.queue_manager.start", new_callable=AsyncMock), \
         patch("app.ia_queue.queue_manager.stop", new_callable=AsyncMock):
        with TestClient(app) as c:
            yield c

    app.dependency_overrides.clear()
