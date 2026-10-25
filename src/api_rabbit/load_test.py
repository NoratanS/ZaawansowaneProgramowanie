"""Send 10, 20 and 30 requests at the same time and report the response times.

Usage: uv run python load_test.py <endpoint> <image_url>
e.g.   uv run python load_test.py analyze_img_sync https://example.com/people.jpg
"""

import statistics
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "http://127.0.0.1:5000"


def timed_get(url: str) -> float | None:
    """Return the response time in seconds, or None if the request failed."""
    start = time.perf_counter()
    try:
        urllib.request.urlopen(url, timeout=120).read()
    except OSError:
        return None
    return time.perf_counter() - start


def main():
    endpoint, image_url = sys.argv[1], sys.argv[2]
    url = f"{API}/{endpoint}?" + urllib.parse.urlencode({"url": image_url})
    for count in (10, 20, 30):
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=count) as pool:
            results = list(pool.map(timed_get, [url] * count))
        total = time.perf_counter() - start
        times = [t for t in results if t is not None]
        print(
            f"{count} requests: total {total:.2f}s, "
            f"min {min(times, default=0):.2f}s, "
            f"avg {statistics.mean(times) if times else 0:.2f}s, "
            f"max {max(times, default=0):.2f}s, "
            f"failed {count - len(times)}"
        )


if __name__ == "__main__":
    main()
