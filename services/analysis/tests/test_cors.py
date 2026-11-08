import pytest

pytestmark = pytest.mark.integration


def _preflight(origin):
    return {
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    }


@pytest.mark.parametrize(
    "results_public_url, origin",
    [
        ("http://localhost:8001", "http://localhost:8001"),
        ("https://pc.example/results-app/", "https://pc.example"),
    ],
)
async def test_preflight_from_the_results_origin_is_allowed_without_a_token(
    client_for, results_public_url, origin
):
    async with client_for(results_public_url, authorized=False) as client:
        response = await client.options("/analyses", headers=_preflight(origin))

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "POST" in response.headers["access-control-allow-methods"]
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed_headers
    assert "content-type" in allowed_headers
    assert "access-control-allow-credentials" not in response.headers


@pytest.mark.parametrize(
    "origin",
    ["http://evil.example", "http://127.0.0.1:8001", "http://localhost:8000"],
)
async def test_preflight_from_another_origin_is_refused(client_for, origin):
    async with client_for("http://localhost:8001", authorized=False) as client:
        response = await client.options("/analyses", headers=_preflight(origin))

    assert "access-control-allow-origin" not in response.headers


async def test_post_from_the_results_origin_carries_the_allow_origin_header(
    client_for,
):
    async with client_for("http://localhost:8001") as client:
        response = await client.post(
            "/analyses",
            json={"image_url": "https://images.example/people.jpg"},
            headers={"Origin": "http://localhost:8001"},
        )

    assert response.status_code == 202
    assert response.headers["access-control-allow-origin"] == "http://localhost:8001"
