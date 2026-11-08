"""Demo burst: submit many Analysis Jobs at once.

    uv run scripts/demo_load.py --token "$TOKEN"

Each job points at an e2e fixture image by its in-Docker URL
(``http://images/<file>``), so the stack must run with ``compose.e2e.yaml``.
A demo tool: no tests.
"""

import argparse
import asyncio
from collections import Counter
from itertools import cycle, islice
from pathlib import Path

import httpx

FIXTURES = Path(__file__).parents[1] / "tests" / "e2e" / "fixtures"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
IMAGES_URL = "http://images"


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a burst of POST /analyses.")
    parser.add_argument("--count", type=int, default=200, help="jobs (default 200)")
    parser.add_argument("--token", required=True, help="client token (issue-token)")
    parser.add_argument(
        "--analysis-url",
        default="http://localhost:8000",
        help="Analysis Service base URL (default http://localhost:8000)",
    )
    args = parser.parse_args()
    images = sorted(p.name for p in FIXTURES.iterdir() if p.suffix in IMAGE_SUFFIXES)
    urls = [f"{IMAGES_URL}/{name}" for name in islice(cycle(images), args.count)]
    statuses = asyncio.run(_send(urls, args.token, args.analysis_url.rstrip("/")))
    print(", ".join(f"{count} x {status}" for status, count in statuses.items()))


async def _send(urls: list[str], token: str, analysis_url: str) -> Counter[str]:
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(headers=headers, timeout=30) as client:

        async def post(url: str) -> str:
            try:
                response = await client.post(
                    f"{analysis_url}/analyses", json={"image_url": url}
                )
            except httpx.HTTPError as exc:
                return type(exc).__name__
            return str(response.status_code)

        return Counter(await asyncio.gather(*(post(url) for url in urls)))


if __name__ == "__main__":
    main()
