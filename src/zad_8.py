import argparse

from zad_7 import fetch_breweries

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="List breweries from Open Brewery DB.")
    parser.add_argument("--city", help="Only show breweries from this city")
    args = parser.parse_args()

    for brewery in fetch_breweries(city=args.city):
        print(brewery)
        print()
