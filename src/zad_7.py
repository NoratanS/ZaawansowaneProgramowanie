import json
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_URL = "https://api.openbrewerydb.org/v1/breweries"


@dataclass
class Brewery:
    id: str
    name: str
    brewery_type: str
    address_1: str | None
    address_2: str | None
    address_3: str | None
    city: str
    state_province: str
    postal_code: str
    country: str
    longitude: float | None
    latitude: float | None
    phone: str | None
    website_url: str | None
    state: str
    street: str | None

    def __str__(self) -> str:
        return (
            f"{self.name} ({self.brewery_type})\n"
            f"  Address: {self.street}, {self.postal_code} {self.city}, "
            f"{self.state_province}, {self.country}\n"
            f"  Coordinates: {self.latitude}, {self.longitude}\n"
            f"  Phone: {self.phone}\n"
            f"  Website: {self.website_url}\n"
            f"  ID: {self.id}"
        )


def fetch_breweries(per_page: int = 20, city: str | None = None) -> list[Brewery]:
    params: dict[str, str | int] = {"per_page": per_page}
    if city:
        params["by_city"] = city
    # The API returns 403 for Python's default User-Agent
    request = Request(
        f"{API_URL}?{urlencode(params)}", headers={"User-Agent": "brewery-script"}
    )
    with urlopen(request) as response:
        data = json.load(response)
    return [Brewery(**item) for item in data]


if __name__ == "__main__":
    for brewery in fetch_breweries():
        print(brewery)
        print()
