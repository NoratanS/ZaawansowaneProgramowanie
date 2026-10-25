import csv
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from python_api.models import Link, Movie, Rating, Tag

DATA_DIR = Path(__file__).parent / "data"

app = FastAPI()


def read_rows(file_name: str) -> list[list[str]]:
    """Return the rows of a CSV file from the data folder, without the header."""
    with open(DATA_DIR / file_name, newline="", encoding="utf-8") as file:
        reader = csv.reader(file)
        next(reader)
        return list(reader)


@app.get("/")
def hello() -> dict:
    return {"hello": "world"}


@app.get("/movies")
def get_movies() -> list[dict]:
    movies = [Movie(*row) for row in read_rows("movies.csv")]
    return [movie.__dict__ for movie in movies]


@app.get("/links")
def get_links() -> list[dict]:
    links = [Link(*row) for row in read_rows("links.csv")]
    return [link.__dict__ for link in links]


@app.get("/ratings")
def get_ratings() -> list[dict]:
    ratings = [Rating(*row) for row in read_rows("ratings.csv")]
    return [rating.__dict__ for rating in ratings]


@app.get("/tags")
def get_tags() -> list[dict]:
    tags = [Tag(*row) for row in read_rows("tags.csv")]
    return [tag.__dict__ for tag in tags]


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5000)
