"""Integration tests for the CRUD endpoints.

Each test gets a fresh in-memory database seeded with the small data set below,
so changes made by one test never leak into another.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from python_api.auth import create_access_token
from python_api.database import get_session
from python_api.main import app
from python_api.models import Base, Link, Movie, Rating, Tag

MOVIES = [
    {"id": 1, "title": "Toy Story (1995)", "genres": "Animation|Children"},
    {"id": 2, "title": "Jumanji (1995)", "genres": "Adventure|Fantasy"},
    {"id": 3, "title": "Heat (1995)", "genres": "Action|Crime"},
]
LINKS = [
    {"movie_id": 1, "imdb_id": "0114709", "tmdb_id": 862},
    {"movie_id": 2, "imdb_id": "0113497", "tmdb_id": 8844},
    {"movie_id": 3, "imdb_id": "0113277", "tmdb_id": None},
]
RATINGS = [
    {"user_id": 1, "movie_id": 1, "rating": 4.0, "timestamp": 964982703},
    {"user_id": 1, "movie_id": 2, "rating": 3.5, "timestamp": 964982224},
    {"user_id": 2, "movie_id": 1, "rating": 5.0, "timestamp": 964983815},
]
TAGS = [
    {"user_id": 1, "movie_id": 1, "tag": "pixar", "timestamp": 1445714994},
    {"user_id": 1, "movie_id": 2, "tag": "board game", "timestamp": 1445714995},
    {"user_id": 2, "movie_id": 1, "tag": "live action/animation", "timestamp": 1},
]


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.execute(insert(Movie), MOVIES)
        session.execute(insert(Link), LINKS)
        session.execute(insert(Rating), RATINGS)
        session.execute(insert(Tag), TAGS)
        session.commit()
    yield engine
    engine.dispose()


@pytest.fixture
def client(engine):
    def get_test_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    # All endpoints need a token; any valid one will do for these tests.
    token = create_access_token("tester", roles=[])
    yield TestClient(app, headers={"Authorization": f"Bearer {token}"})
    app.dependency_overrides.clear()


@pytest.fixture
def db(engine):
    """Direct database access, to check what the API really stored."""
    with Session(engine) as session:
        yield session


# --- movies ---


def test_list_movies(client):
    response = client.get("/movies")
    assert response.status_code == 200
    assert len(response.json()) == len(MOVIES)
    assert response.json() == MOVIES


def test_get_movie(client):
    response = client.get("/movies/2")
    assert response.status_code == 200
    assert response.json() == MOVIES[1]


def test_get_movie_not_found(client):
    response = client.get("/movies/999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Movie not found"}


def test_create_movie(client, db):
    new_movie = {"id": 4, "title": "Casino (1995)", "genres": "Crime|Drama"}
    response = client.post("/movies", json=new_movie)
    assert response.status_code == 201
    assert response.json() == new_movie
    assert db.get(Movie, 4).to_dict() == new_movie
    assert len(client.get("/movies").json()) == len(MOVIES) + 1


def test_create_movie_duplicate_id(client, db):
    response = client.post("/movies", json={"id": 1, "title": "X", "genres": "Y"})
    assert response.status_code == 409
    assert db.get(Movie, 1).title == "Toy Story (1995)"


def test_create_movie_invalid_body(client):
    response = client.post("/movies", json={"id": 4})
    assert response.status_code == 422


def test_update_movie(client, db):
    changes = {"title": "Toy Story", "genres": "Comedy"}
    response = client.put("/movies/1", json=changes)
    assert response.status_code == 200
    assert response.json() == {"id": 1, **changes}
    movie = db.get(Movie, 1)
    assert movie.title == "Toy Story"
    assert movie.genres == "Comedy"


def test_update_movie_not_found(client, db):
    response = client.put("/movies/999", json={"title": "X", "genres": "Y"})
    assert response.status_code == 404
    assert db.get(Movie, 999) is None


def test_delete_movie(client, db):
    response = client.delete("/movies/3")
    assert response.status_code == 204
    assert db.get(Movie, 3) is None
    assert client.get("/movies/3").status_code == 404
    assert len(client.get("/movies").json()) == len(MOVIES) - 1


def test_delete_movie_not_found(client):
    assert client.delete("/movies/999").status_code == 404


# --- links ---


def test_list_links(client):
    response = client.get("/links")
    assert response.status_code == 200
    assert len(response.json()) == len(LINKS)
    assert response.json() == LINKS


def test_get_link(client):
    response = client.get("/links/3")
    assert response.status_code == 200
    assert response.json() == LINKS[2]
    assert response.json()["tmdb_id"] is None


def test_get_link_not_found(client):
    response = client.get("/links/999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Link not found"}


def test_create_link(client, db):
    db.add(Movie(id=4, title="Casino (1995)", genres="Crime|Drama"))
    db.commit()
    new_link = {"movie_id": 4, "imdb_id": "0112641", "tmdb_id": 524}
    response = client.post("/links", json=new_link)
    assert response.status_code == 201
    assert response.json() == new_link
    assert db.get(Link, 4).to_dict() == new_link


def test_create_link_duplicate(client, db):
    response = client.post("/links", json={"movie_id": 1, "imdb_id": "1"})
    assert response.status_code == 409
    assert db.get(Link, 1).imdb_id == "0114709"


def test_update_link(client, db):
    response = client.put("/links/3", json={"imdb_id": "0113277", "tmdb_id": 949})
    assert response.status_code == 200
    assert response.json() == {"movie_id": 3, "imdb_id": "0113277", "tmdb_id": 949}
    assert db.get(Link, 3).tmdb_id == 949


def test_update_link_not_found(client):
    response = client.put("/links/999", json={"imdb_id": "1", "tmdb_id": 1})
    assert response.status_code == 404


def test_delete_link(client, db):
    response = client.delete("/links/1")
    assert response.status_code == 204
    assert db.get(Link, 1) is None
    assert len(client.get("/links").json()) == len(LINKS) - 1


def test_delete_link_not_found(client):
    assert client.delete("/links/999").status_code == 404


# --- ratings ---


def test_list_ratings(client):
    response = client.get("/ratings")
    assert response.status_code == 200
    assert len(response.json()) == len(RATINGS)
    assert response.json() == RATINGS


def test_get_rating(client):
    response = client.get("/ratings/1/2")
    assert response.status_code == 200
    assert response.json() == RATINGS[1]


def test_get_rating_not_found(client):
    # Both ids exist, but user 2 has not rated movie 2.
    response = client.get("/ratings/2/2")
    assert response.status_code == 404
    assert response.json() == {"detail": "Rating not found"}


def test_create_rating(client, db):
    new_rating = {"user_id": 2, "movie_id": 3, "rating": 2.5, "timestamp": 100}
    response = client.post("/ratings", json=new_rating)
    assert response.status_code == 201
    assert response.json() == new_rating
    assert db.get(Rating, (2, 3)).to_dict() == new_rating
    assert len(client.get("/ratings").json()) == len(RATINGS) + 1


def test_create_rating_duplicate(client, db):
    duplicate = {"user_id": 1, "movie_id": 1, "rating": 1.0, "timestamp": 1}
    response = client.post("/ratings", json=duplicate)
    assert response.status_code == 409
    assert db.get(Rating, (1, 1)).rating == 4.0


def test_update_rating(client, db):
    response = client.put("/ratings/1/1", json={"rating": 1.5, "timestamp": 200})
    assert response.status_code == 200
    assert response.json() == {
        "user_id": 1,
        "movie_id": 1,
        "rating": 1.5,
        "timestamp": 200,
    }
    rating = db.get(Rating, (1, 1))
    assert rating.rating == 1.5
    assert rating.timestamp == 200


def test_update_rating_not_found(client):
    response = client.put("/ratings/2/2", json={"rating": 1.0, "timestamp": 1})
    assert response.status_code == 404


def test_delete_rating(client, db):
    response = client.delete("/ratings/2/1")
    assert response.status_code == 204
    assert db.get(Rating, (2, 1)) is None
    # Other ratings of the same movie stay untouched.
    assert db.get(Rating, (1, 1)) is not None


def test_delete_rating_not_found(client):
    assert client.delete("/ratings/2/2").status_code == 404


# --- tags ---


def test_list_tags(client):
    response = client.get("/tags")
    assert response.status_code == 200
    assert len(response.json()) == len(TAGS)
    assert response.json() == TAGS


def test_get_tag(client):
    response = client.get("/tags/1/2/board game")
    assert response.status_code == 200
    assert response.json() == TAGS[1]


def test_get_tag_with_slash(client):
    response = client.get("/tags/2/1/live action/animation")
    assert response.status_code == 200
    assert response.json() == TAGS[2]


def test_get_tag_not_found(client):
    response = client.get("/tags/1/1/no such tag")
    assert response.status_code == 404
    assert response.json() == {"detail": "Tag not found"}


def test_create_tag(client, db):
    new_tag = {"user_id": 1, "movie_id": 3, "tag": "heist", "timestamp": 300}
    response = client.post("/tags", json=new_tag)
    assert response.status_code == 201
    assert response.json() == new_tag
    assert db.get(Tag, (1, 3, "heist")).to_dict() == new_tag
    assert len(client.get("/tags").json()) == len(TAGS) + 1


def test_create_tag_duplicate(client):
    duplicate = {"user_id": 1, "movie_id": 1, "tag": "pixar", "timestamp": 1}
    response = client.post("/tags", json=duplicate)
    assert response.status_code == 409


def test_update_tag(client, db):
    response = client.put("/tags/1/1/pixar", json={"timestamp": 400})
    assert response.status_code == 200
    assert response.json() == {
        "user_id": 1,
        "movie_id": 1,
        "tag": "pixar",
        "timestamp": 400,
    }
    assert db.get(Tag, (1, 1, "pixar")).timestamp == 400


def test_update_tag_not_found(client):
    response = client.put("/tags/1/1/no such tag", json={"timestamp": 1})
    assert response.status_code == 404


def test_delete_tag(client, db):
    response = client.delete("/tags/1/1/pixar")
    assert response.status_code == 204
    assert db.get(Tag, (1, 1, "pixar")) is None
    assert len(client.get("/tags").json()) == len(TAGS) - 1


def test_delete_tag_not_found(client):
    assert client.delete("/tags/1/1/no such tag").status_code == 404
