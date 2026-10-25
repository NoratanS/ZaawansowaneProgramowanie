from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    def to_dict(self) -> dict:
        return {column.name: getattr(self, column.name) for column in self.__table__.c}


class Movie(Base):
    __tablename__ = "movies"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    genres: Mapped[str]


class Link(Base):
    __tablename__ = "links"

    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id"), primary_key=True)
    # Kept as text: IMDb ids have leading zeros, e.g. "0114709".
    imdb_id: Mapped[str]
    # A few movies have no TMDB id in the source data.
    tmdb_id: Mapped[int | None]


class Rating(Base):
    __tablename__ = "ratings"

    user_id: Mapped[int] = mapped_column(primary_key=True)
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id"), primary_key=True)
    rating: Mapped[float]
    timestamp: Mapped[int]


class Tag(Base):
    __tablename__ = "tags"

    user_id: Mapped[int] = mapped_column(primary_key=True)
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id"), primary_key=True)
    tag: Mapped[str] = mapped_column(primary_key=True)
    timestamp: Mapped[int]
