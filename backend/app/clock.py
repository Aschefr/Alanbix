"""Current time in naive UTC, the way the database stores dates."""
import datetime


def utcnow() -> datetime.datetime:
    """Replaces datetime.utcnow(), deprecated since Python 3.12: same naive UTC value."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
