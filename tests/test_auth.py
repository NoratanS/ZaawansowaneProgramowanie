"""Integration tests for login, users and JWT protection.

Every test sends real HTTP requests through TestClient to a fresh in-memory
database that holds one admin and one regular user.
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from python_api.auth import ALGORITHM, ROLE_ADMIN, SECRET_KEY, hash_password
from python_api.database import get_session
from python_api.main import app
from python_api.models import Base, User

ADMIN = {"username": "admin", "password": "admin-pass"}
REGULAR = {"username": "alice", "password": "alice-pass"}


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                User(
                    username=ADMIN["username"],
                    password_hash=hash_password(ADMIN["password"]),
                    roles=[ROLE_ADMIN],
                ),
                User(
                    username=REGULAR["username"],
                    password_hash=hash_password(REGULAR["password"]),
                    roles=[],
                ),
            ]
        )
        session.commit()
    yield engine
    engine.dispose()


@pytest.fixture
def client(engine):
    def get_test_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def login(client, credentials: dict) -> dict:
    """Log in and return the Authorization header for the received token."""
    response = client.post("/login", json=credentials)
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


# --- /login ---


def test_login_returns_valid_token(client):
    response = client.post("/login", json=ADMIN)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"

    payload = jwt.decode(body["access_token"], SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == "admin"
    assert payload["roles"] == [ROLE_ADMIN]
    assert payload["exp"] > payload["iat"]


def test_login_wrong_password(client):
    response = client.post("/login", json={"username": "admin", "password": "nope"})
    assert response.status_code == 401
    assert "access_token" not in response.json()


def test_login_unknown_user(client):
    response = client.post("/login", json={"username": "ghost", "password": "x"})
    assert response.status_code == 401


def test_login_missing_fields(client):
    response = client.post("/login", json={"username": "admin"})
    assert response.status_code == 422


# --- POST /users ---


def test_admin_can_create_user(client, engine):
    new_user = {"username": "bob", "password": "bob-pass", "roles": []}
    response = client.post("/users", json=new_user, headers=login(client, ADMIN))
    assert response.status_code == 201
    assert response.json() == {"id": 3, "username": "bob", "roles": []}
    assert "password" not in response.text

    with Session(engine) as session:
        stored = session.scalar(select(User).where(User.username == "bob"))
        assert stored.password_hash != "bob-pass"

    # The new user can log in right away.
    assert client.post("/login", json=new_user).status_code == 200


def test_admin_can_create_another_admin(client):
    new_admin = {"username": "carol", "password": "pw", "roles": [ROLE_ADMIN]}
    response = client.post("/users", json=new_admin, headers=login(client, ADMIN))
    assert response.status_code == 201

    carol_headers = login(client, new_admin)
    response = client.post(
        "/users", json={"username": "dave", "password": "pw"}, headers=carol_headers
    )
    assert response.status_code == 201


def test_user_without_admin_role_cannot_create_user(client):
    response = client.post(
        "/users",
        json={"username": "bob", "password": "pw"},
        headers=login(client, REGULAR),
    )
    assert response.status_code == 403
    assert (
        client.post("/login", json={"username": "bob", "password": "pw"}).status_code
        == 401
    )


def test_create_user_without_token(client):
    response = client.post("/users", json={"username": "bob", "password": "pw"})
    assert response.status_code == 401


def test_create_duplicate_user(client):
    response = client.post("/users", json=REGULAR, headers=login(client, ADMIN))
    assert response.status_code == 409


# --- /user_details ---


def test_user_details_returns_token_payload(client):
    response = client.get("/user_details", headers=login(client, REGULAR))
    assert response.status_code == 200
    body = response.json()
    assert body["sub"] == "alice"
    assert body["roles"] == []
    assert {"iat", "exp"} <= body.keys()


def test_user_details_without_token(client):
    response = client.get("/user_details")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_user_details_with_garbage_token(client):
    response = client.get(
        "/user_details", headers={"Authorization": "Bearer not-a-jwt"}
    )
    assert response.status_code == 401


def test_user_details_with_wrong_signature(client):
    token = jwt.encode(
        {"sub": "admin", "roles": [ROLE_ADMIN]},
        "some-other-secret-key-that-is-long-enough",
        algorithm=ALGORITHM,
    )
    response = client.get("/user_details", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_user_details_with_expired_token(client):
    past = datetime.now(UTC) - timedelta(hours=1)
    token = jwt.encode(
        {"sub": "alice", "roles": [], "iat": past, "exp": past + timedelta(minutes=1)},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    response = client.get("/user_details", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_user_details_without_bearer_prefix(client):
    token = login(client, REGULAR)["Authorization"].removeprefix("Bearer ")
    response = client.get("/user_details", headers={"Authorization": token})
    assert response.status_code == 401


# --- the rest of the API ---


@pytest.mark.parametrize("path", ["/", "/movies", "/links", "/ratings", "/tags"])
def test_other_endpoints_require_token(client, path):
    assert client.get(path).status_code == 401
    assert client.get(path, headers=login(client, REGULAR)).status_code == 200
