"""Tournaments an administrator hid from the players."""
from sqlalchemy import or_
from sqlalchemy.orm import Session

from . import models


def visible_tournaments(db: Session):
    """Query on the tournaments players may see (not hidden)."""
    return db.query(models.Tournament).filter(
        or_(models.Tournament.is_hidden == False, models.Tournament.is_hidden.is_(None))  # noqa: E712
    )
