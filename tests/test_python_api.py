import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from python_api.auth import create_access_token
from python_api.database import get_session
from python_api.load_data import load
from python_api.main import app


@pytest.fixture(scope="module")
def client():
    # In-memory database shared by all connections, filled from the CSV files.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    load(engine)

    def get_test_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    # All endpoints need a token; any valid one will do for these tests.
    token = create_access_token("tester", roles=[])
    yield TestClient(app, headers={"Authorization": f"Bearer {token}"})
    app.dependency_overrides.clear()


def test_hello(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"hello": "world"}


def test_movies(client):
    movies = client.get("/movies").json()
    assert len(movies) == 9742
    assert movies[0] == {
        "id": 1,
        "title": "Toy Story (1995)",
        "genres": "Adventure|Animation|Children|Comedy|Fantasy",
    }


def test_links(client):
    links = client.get("/links").json()
    assert len(links) == 9742
    assert links[0] == {"movie_id": 1, "imdb_id": "0114709", "tmdb_id": 862}
    # Empty tmdbId values in the CSV become null.
    assert sum(link["tmdb_id"] is None for link in links) == 8


def test_ratings(client):
    ratings = client.get("/ratings").json()
    assert len(ratings) == 100836
    assert ratings[0] == {
        "user_id": 1,
        "movie_id": 1,
        "rating": 4.0,
        "timestamp": 964982703,
    }


def test_tags(client):
    tags = client.get("/tags").json()
    assert len(tags) == 3683
    assert tags[0] == {
        "user_id": 2,
        "movie_id": 60756,
        "tag": "Highly quotable",
        "timestamp": 1445714996,
    }
