"""Request bodies for the create (POST) and update (PUT) endpoints.

Update bodies hold only the non-key fields; the key comes from the URL.
"""

from pydantic import BaseModel


class MovieUpdate(BaseModel):
    title: str
    genres: str


class MovieCreate(MovieUpdate):
    id: int


class LinkUpdate(BaseModel):
    imdb_id: str
    tmdb_id: int | None = None


class LinkCreate(LinkUpdate):
    movie_id: int


class RatingUpdate(BaseModel):
    rating: float
    timestamp: int


class RatingCreate(RatingUpdate):
    user_id: int
    movie_id: int


class TagUpdate(BaseModel):
    timestamp: int


class TagCreate(TagUpdate):
    user_id: int
    movie_id: int
    tag: str


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreate(LoginRequest):
    roles: list[str] = []
