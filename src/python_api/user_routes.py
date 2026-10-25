from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from python_api.auth import (
    TokenPayload,
    create_access_token,
    hash_password,
    require_admin,
    verify_password,
)
from python_api.models import User
from python_api.routes import SessionDep
from python_api.schemas import LoginRequest, UserCreate

router = APIRouter()


@router.post("/login")
def login(credentials: LoginRequest, session: SessionDep) -> dict:
    user = session.scalar(select(User).where(User.username == credentials.username))
    # Same error for an unknown user and a wrong password, so the response
    # does not reveal which usernames exist.
    if user is None or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token(user.username, user.roles)
    return {"access_token": token, "token_type": "bearer"}


@router.post("/users", status_code=201, dependencies=[Depends(require_admin)])
def create_user(data: UserCreate, session: SessionDep) -> dict:
    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        roles=data.roles,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="User already exists")
    # Never send the password hash back.
    return {"id": user.id, "username": user.username, "roles": user.roles}


@router.get("/user_details")
def user_details(payload: TokenPayload) -> dict:
    return payload
