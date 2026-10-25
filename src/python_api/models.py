class Movie:
    def __init__(self, id: str, title: str, genres: str) -> None:
        self.id = id
        self.title = title
        self.genres = genres


class Link:
    def __init__(self, movie_id: str, imdb_id: str, tmdb_id: str) -> None:
        self.movie_id = movie_id
        self.imdb_id = imdb_id
        self.tmdb_id = tmdb_id


class Rating:
    def __init__(
        self, user_id: str, movie_id: str, rating: str, timestamp: str
    ) -> None:
        self.user_id = user_id
        self.movie_id = movie_id
        self.rating = rating
        self.timestamp = timestamp


class Tag:
    def __init__(self, user_id: str, movie_id: str, tag: str, timestamp: str) -> None:
        self.user_id = user_id
        self.movie_id = movie_id
        self.tag = tag
        self.timestamp = timestamp
