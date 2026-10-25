from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from python_api.database import get_session
from python_api.models import Link, Movie, Rating, Tag

app = FastAPI()

SessionDep = Annotated[Session, Depends(get_session)]


@app.get("/")
def hello() -> dict:
    return {"hello": "world"}


@app.get("/movies")
def get_movies(session: SessionDep) -> list[dict]:
    movies = session.scalars(select(Movie).order_by(Movie.id))
    return [movie.to_dict() for movie in movies]


@app.get("/links")
def get_links(session: SessionDep) -> list[dict]:
    links = session.scalars(select(Link).order_by(Link.movie_id))
    return [link.to_dict() for link in links]


@app.get("/ratings")
def get_ratings(session: SessionDep) -> list[dict]:
    ratings = session.scalars(select(Rating).order_by(Rating.user_id, Rating.movie_id))
    return [rating.to_dict() for rating in ratings]


@app.get("/tags")
def get_tags(session: SessionDep) -> list[dict]:
    tags = session.scalars(select(Tag).order_by(Tag.user_id, Tag.movie_id, Tag.tag))
    return [tag.to_dict() for tag in tags]


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5000)
