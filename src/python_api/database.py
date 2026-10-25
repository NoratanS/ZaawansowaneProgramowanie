from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

DB_PATH = Path(__file__).parent / "movies.db"

engine = create_engine(f"sqlite:///{DB_PATH}")


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one database session per request."""
    with Session(engine) as session:
        yield session
