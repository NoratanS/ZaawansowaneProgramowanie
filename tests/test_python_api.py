from fastapi.testclient import TestClient

from python_api.main import app

client = TestClient(app)


def test_hello():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"hello": "world"}


def test_movies():
    movies = client.get("/movies").json()
    assert movies[0] == {
        "id": "1",
        "title": "Toy Story (1995)",
        "genres": "Adventure|Animation|Children|Comedy|Fantasy",
    }


def test_links():
    links = client.get("/links").json()
    assert links[0] == {"movie_id": "1", "imdb_id": "0114709", "tmdb_id": "862"}


def test_ratings():
    ratings = client.get("/ratings").json()
    assert ratings[0] == {
        "user_id": "1",
        "movie_id": "1",
        "rating": "4.0",
        "timestamp": "964982703",
    }


def test_tags():
    tags = client.get("/tags").json()
    assert tags[0] == {
        "user_id": "2",
        "movie_id": "60756",
        "tag": "funny",
        "timestamp": "1445714994",
    }
