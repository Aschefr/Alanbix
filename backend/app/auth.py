import os
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from . import models, database

# Config
def _load_or_create_secret_key() -> str:
    """Use SECRET_KEY from env, otherwise a random key persisted next to the database."""
    env_key = os.getenv("SECRET_KEY", "").strip()
    if env_key:
        return env_key
    import secrets
    data_dir = os.path.dirname(os.getenv("DATABASE_PATH", "/app/data/alanbix.db"))
    key_path = os.path.join(data_dir, ".secret_key")
    try:
        with open(key_path, "r", encoding="utf-8") as f:
            stored = f.read().strip()
        if stored:
            return stored
    except FileNotFoundError:
        pass
    new_key = secrets.token_hex(32)
    os.makedirs(data_dir, exist_ok=True)
    with open(key_path, "w", encoding="utf-8") as f:
        f.write(new_key)
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    print(f"[Auth] Generated new secret key at {key_path}")
    return new_key

SECRET_KEY = _load_or_create_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 600 # Long duration for LAN

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(db: Session = Depends(database.get_db), token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token and token.startswith("dev_"):
        device = db.query(models.Device).filter(models.Device.token == token).first()
        if not device:
            raise credentials_exception
        user = db.query(models.User).filter(models.User.id == device.user_id).first()
        if user is None:
            raise credentials_exception
        device.last_seen = datetime.utcnow()
        db.commit()
        return user

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        raise credentials_exception
    
    # Track online presence in memory (zero SQLite write lock latency)
    from .database import ACTIVE_USERS
    ACTIVE_USERS[user.id] = datetime.utcnow()
            
    return user

async def get_current_admin(current_user: models.User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user


def get_user_id_from_token(token: str, db: Optional[Session] = None) -> Optional[int]:
    """Validate a JWT token or persistent device token and extract the corresponding user_id (for WebSocket/push auth)."""
    if not token or not isinstance(token, str):
        return None

    # Check for long-lived device token
    if token.startswith("dev_"):
        try:
            if db is not None:
                device = db.query(models.Device).filter(models.Device.token == token).first()
                if device:
                    device.last_seen = datetime.utcnow()
                    db.commit()
                    return device.user_id
                return None
            from .database import SessionLocal
            with SessionLocal() as session:
                device = session.query(models.Device).filter(models.Device.token == token).first()
                if device:
                    device.last_seen = datetime.utcnow()
                    session.commit()
                    return device.user_id
                return None
        except Exception:
            return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username:
            return None
        if db is not None:
            user = db.query(models.User).filter(models.User.username == username).first()
            return user.id if user else None
        from .database import SessionLocal
        with SessionLocal() as session:
            user = session.query(models.User).filter(models.User.username == username).first()
            return user.id if user else None
    except Exception:
        return None
