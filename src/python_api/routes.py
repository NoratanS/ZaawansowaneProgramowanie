from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from python_api.database import get_session
from python_api.models import Base, Link, Movie, Rating, Tag
from python_api.schemas import (
    LinkCreate,
    LinkUpdate,
    MovieCreate,
    MovieUpdate,
    RatingCreate,
    RatingUpdate,
    TagCreate,
    TagUpdate,
)

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]


def get_or_404(session: Session, model: type[Base], key: object) -> Base:
    item = session.get(model, key)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return item


def create_item(session: Session, model: type[Base], data: BaseModel) -> dict:
    item = model(**data.model_dump())
    session.add(item)
    try:
        session.commit()
    except IntegrityError:
        raise HTTPException(status_code=409, detail=f"{model.__name__} already exists")
    return item.to_dict()


def update_item(session: Session, item: Base, data: BaseModel) -> dict:
    for field, value in data.model_dump().items():
        setattr(item, field, value)
    session.commit()
    return item.to_dict()


def delete_item(session: Session, item: Base) -> None:
    session.delete(item)
    session.commit()


@router.get("/movies")
def get_movies(session: SessionDep) -> list[dict]:
    movies = session.scalars(select(Movie).order_by(Movie.id))
    return [movie.to_dict() for movie in movies]


@router.post("/movies", status_code=201)
def create_movie(movie: MovieCreate, session: SessionDep) -> dict:
    return create_item(session, Movie, movie)


@router.get("/movies/{movie_id}")
def get_movie(movie_id: int, session: SessionDep) -> dict:
    return get_or_404(session, Movie, movie_id).to_dict()


@router.put("/movies/{movie_id}")
def update_movie(movie_id: int, movie: MovieUpdate, session: SessionDep) -> dict:
    return update_item(session, get_or_404(session, Movie, movie_id), movie)


@router.delete("/movies/{movie_id}", status_code=204)
def delete_movie(movie_id: int, session: SessionDep) -> None:
    delete_item(session, get_or_404(session, Movie, movie_id))


@router.get("/links")
def get_links(session: SessionDep) -> list[dict]:
    links = session.scalars(select(Link).order_by(Link.movie_id))
    return [link.to_dict() for link in links]


@router.post("/links", status_code=201)
def create_link(link: LinkCreate, session: SessionDep) -> dict:
    return create_item(session, Link, link)


@router.get("/links/{movie_id}")
def get_link(movie_id: int, session: SessionDep) -> dict:
    return get_or_404(session, Link, movie_id).to_dict()


@router.put("/links/{movie_id}")
def update_link(movie_id: int, link: LinkUpdate, session: SessionDep) -> dict:
    return update_item(session, get_or_404(session, Link, movie_id), link)


@router.delete("/links/{movie_id}", status_code=204)
def delete_link(movie_id: int, session: SessionDep) -> None:
    delete_item(session, get_or_404(session, Link, movie_id))


@router.get("/ratings")
def get_ratings(session: SessionDep) -> list[dict]:
    ratings = session.scalars(select(Rating).order_by(Rating.user_id, Rating.movie_id))
    return [rating.to_dict() for rating in ratings]


# A rating is identified by its composite primary key: (user_id, movie_id).
@router.post("/ratings", status_code=201)
def create_rating(rating: RatingCreate, session: SessionDep) -> dict:
    return create_item(session, Rating, rating)


@router.get("/ratings/{user_id}/{movie_id}")
def get_rating(user_id: int, movie_id: int, session: SessionDep) -> dict:
    return get_or_404(session, Rating, (user_id, movie_id)).to_dict()


@router.put("/ratings/{user_id}/{movie_id}")
def update_rating(
    user_id: int, movie_id: int, rating: RatingUpdate, session: SessionDep
) -> dict:
    item = get_or_404(session, Rating, (user_id, movie_id))
    return update_item(session, item, rating)


@router.delete("/ratings/{user_id}/{movie_id}", status_code=204)
def delete_rating(user_id: int, movie_id: int, session: SessionDep) -> None:
    delete_item(session, get_or_404(session, Rating, (user_id, movie_id)))


@router.get("/tags")
def get_tags(session: SessionDep) -> list[dict]:
    tags = session.scalars(select(Tag).order_by(Tag.user_id, Tag.movie_id, Tag.tag))
    return [tag.to_dict() for tag in tags]


# A tag is identified by its composite primary key: (user_id, movie_id, tag).
# `:path` lets the tag text contain slashes, e.g. "live action/animation".
@router.post("/tags", status_code=201)
def create_tag(tag: TagCreate, session: SessionDep) -> dict:
    return create_item(session, Tag, tag)


@router.get("/tags/{user_id}/{movie_id}/{tag:path}")
def get_tag(user_id: int, movie_id: int, tag: str, session: SessionDep) -> dict:
    return get_or_404(session, Tag, (user_id, movie_id, tag)).to_dict()


@router.put("/tags/{user_id}/{movie_id}/{tag:path}")
def update_tag(
    user_id: int, movie_id: int, tag: str, data: TagUpdate, session: SessionDep
) -> dict:
    item = get_or_404(session, Tag, (user_id, movie_id, tag))
    return update_item(session, item, data)


@router.delete("/tags/{user_id}/{movie_id}/{tag:path}", status_code=204)
def delete_tag(user_id: int, movie_id: int, tag: str, session: SessionDep) -> None:
    delete_item(session, get_or_404(session, Tag, (user_id, movie_id, tag)))
