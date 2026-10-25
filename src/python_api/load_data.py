"""Create the database schema and load the CSV files into it.

Run from the src folder: uv run python -m python_api.load_data
"""

import csv
import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, insert
from sqlalchemy.orm import Session

from python_api.auth import ROLE_ADMIN, hash_password
from python_api.database import engine
from python_api.models import Base, Link, Movie, Rating, Tag, User

DATA_DIR = Path(__file__).parent / "data"


def read_rows(file_name: str) -> Iterator[dict[str, str]]:
    """Yield the rows of a CSV file from the data folder as dicts."""
    with open(DATA_DIR / file_name, newline="", encoding="utf-8") as file:
        yield from csv.DictReader(file)


def load(target: Engine) -> None:
    """Recreate all tables, fill them with the CSV data and add an admin user.

    The admin logs in as "admin" with the ADMIN_PASSWORD env var (default "admin").
    """
    Base.metadata.drop_all(target)
    Base.metadata.create_all(target)

    movies = [
        {"id": int(row["movieId"]), "title": row["title"], "genres": row["genres"]}
        for row in read_rows("movies.csv")
    ]
    links = [
        {
            "movie_id": int(row["movieId"]),
            "imdb_id": row["imdbId"],
            "tmdb_id": int(row["tmdbId"]) if row["tmdbId"] else None,
        }
        for row in read_rows("links.csv")
    ]
    ratings = [
        {
            "user_id": int(row["userId"]),
            "movie_id": int(row["movieId"]),
            "rating": float(row["rating"]),
            "timestamp": int(row["timestamp"]),
        }
        for row in read_rows("ratings.csv")
    ]
    tags = [
        {
            "user_id": int(row["userId"]),
            "movie_id": int(row["movieId"]),
            "tag": row["tag"],
            "timestamp": int(row["timestamp"]),
        }
        for row in read_rows("tags.csv")
    ]

    with Session(target) as session:
        session.execute(insert(Movie), movies)
        session.execute(insert(Link), links)
        session.execute(insert(Rating), ratings)
        session.execute(insert(Tag), tags)
        session.add(
            User(
                username="admin",
                password_hash=hash_password(os.environ.get("ADMIN_PASSWORD", "admin")),
                roles=[ROLE_ADMIN],
            )
        )
        session.commit()


if __name__ == "__main__":
    load(engine)
