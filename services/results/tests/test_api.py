import asyncpg
import pytest

import result_cases

pytestmark = pytest.mark.integration


async def test_health_answers_without_the_database(unreachable_db_client):
    response = await unreachable_db_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


SUCCEEDED = result_cases.load("succeeded-with-boxes").body


async def test_put_stores_a_new_result(client):
    response = await client.put(f"/results/{SUCCEEDED['job_id']}", json=SUCCEEDED)

    assert response.status_code == 201
    assert response.json() == SUCCEEDED


async def test_repeat_put_returns_the_stored_result_unchanged(client):
    url = f"/results/{SUCCEEDED['job_id']}"
    await client.put(url, json=SUCCEEDED)
    redelivered = {**SUCCEEDED, "person_count": 0, "detections": []}

    response = await client.put(url, json=redelivered)

    assert response.status_code == 200
    assert response.json() == SUCCEEDED
    assert (await client.get(url)).json() == SUCCEEDED


async def test_repeat_put_of_the_same_body_returns_200(client):
    url = f"/results/{SUCCEEDED['job_id']}"
    await client.put(url, json=SUCCEEDED)

    response = await client.put(url, json=SUCCEEDED)

    assert response.status_code == 200
    assert response.json() == SUCCEEDED


async def test_get_returns_a_stored_result(client):
    await client.put(f"/results/{SUCCEEDED['job_id']}", json=SUCCEEDED)

    response = await client.get(f"/results/{SUCCEEDED['job_id']}")

    assert response.status_code == 200
    assert response.json() == SUCCEEDED


async def test_get_of_an_unknown_id_is_404(client):
    response = await client.get("/results/7d3f5c1a-0000-4000-8000-000000000000")

    assert response.status_code == 404


async def test_get_of_a_non_uuid_is_422(client):
    response = await client.get("/results/not-a-uuid")

    assert response.status_code == 422


FAILED_RESULT = result_cases.load("failed-not-an-image").body


async def test_put_stores_a_failed_result(client):
    response = await client.put(
        f"/results/{FAILED_RESULT['job_id']}", json=FAILED_RESULT
    )

    assert response.status_code == 201
    assert response.json() == FAILED_RESULT


@pytest.mark.parametrize("case", result_cases.all_cases(), ids=lambda case: case.name)
async def test_put_answers_each_case_as_the_model_does(client, case):
    # Catches a SQL CHECK that is stricter or looser than the model.
    url = f"/results/{case.body['job_id']}"

    response = await client.put(url, json=case.body)

    if case.results_service == "accept":
        assert response.status_code == 201
        assert (await client.get(url)).json() == response.json()
    else:
        assert response.status_code == 422
        assert (await client.get(url)).status_code == 404


async def test_put_rejects_a_body_whose_id_differs_from_the_path(client):
    url = f"/results/{SUCCEEDED['job_id']}"
    body = {**SUCCEEDED, "job_id": "11111111-2222-4333-8444-555555555555"}

    response = await client.put(url, json=body)

    assert response.status_code == 422
    assert (await client.get(url)).status_code == 404


async def test_timestamps_come_back_in_utc(client):
    body = {**SUCCEEDED, "requested_at": "2026-10-25T14:00:00+02:00"}

    response = await client.put(f"/results/{SUCCEEDED['job_id']}", json=body)

    assert response.json()["requested_at"] == "2026-10-25T12:00:00Z"


def _failed_with_id(n):
    return {**FAILED_RESULT, "job_id": f"00000000-0000-4000-8000-{n:012d}"}


async def _store_all_at_the_same_moment(database_url):
    dsn = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    connection = await asyncpg.connect(dsn)
    try:
        await connection.execute("UPDATE results SET stored_at = now()")
    finally:
        await connection.close()


async def _put_all(client, bodies):
    for body in bodies:
        response = await client.put(f"/results/{body['job_id']}", json=body)
        assert response.status_code == 201


async def test_list_of_nothing_is_an_empty_array(client):
    response = await client.get("/results")

    assert response.status_code == 200
    assert response.json() == []


async def test_list_is_newest_stored_first_and_includes_failed(client):
    await _put_all(client, [SUCCEEDED, FAILED_RESULT])

    response = await client.get("/results")

    assert response.json() == [FAILED_RESULT, SUCCEEDED]


async def test_list_breaks_stored_at_ties_by_job_id(client, database_url):
    first, second, third = (_failed_with_id(n) for n in range(3))
    # Neither the insertion order nor its reverse matches job_id order.
    await _put_all(client, [third, first, second])
    await _store_all_at_the_same_moment(database_url)

    response = await client.get("/results")

    assert response.json() == [first, second, third]


async def test_list_pages_with_limit_and_offset(client):
    first, second, third = (_failed_with_id(n) for n in range(3))
    await _put_all(client, [first, second, third])

    response = await client.get("/results", params={"limit": 1, "offset": 1})

    assert response.json() == [second]


async def test_list_offset_past_the_end_is_an_empty_array(client):
    await _put_all(client, [SUCCEEDED])

    response = await client.get("/results", params={"offset": 1})

    assert response.status_code == 200
    assert response.json() == []


async def test_list_returns_50_by_default(client):
    await _put_all(client, [_failed_with_id(n) for n in range(51)])

    response = await client.get("/results")

    assert len(response.json()) == 50


async def test_list_accepts_the_largest_limit(client):
    response = await client.get("/results", params={"limit": 200})

    assert response.status_code == 200


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 201},
        {"limit": "ten"},
        {"offset": -1},
    ],
    ids=["limit 0", "limit 201", "limit not a number", "negative offset"],
)
async def test_list_rejects_out_of_range_paging(client, params):
    response = await client.get("/results", params=params)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "method, url, body",
    [
        ("PUT", f"/results/{SUCCEEDED['job_id']}", SUCCEEDED),
        ("GET", f"/results/{SUCCEEDED['job_id']}", None),
        ("GET", "/results", None),
    ],
    ids=["put", "get one", "list"],
)
async def test_unreachable_database_is_503(unreachable_db_client, method, url, body):
    response = await unreachable_db_client.request(method, url, json=body)

    assert response.status_code == 503


async def test_database_refusing_connections_is_503(fatal_on_connect_db_client):
    response = await fatal_on_connect_db_client.get("/results")

    assert response.status_code == 503


async def _terminate_other_connections(database_url):
    dsn = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    connection = await asyncpg.connect(dsn)
    try:
        await connection.execute(
            "SELECT pg_terminate_backend(pid, 5000) FROM pg_stat_activity"
            " WHERE datname = current_database() AND pid <> pg_backend_pid()"
        )
    finally:
        await connection.close()


async def test_requests_recover_after_pooled_connections_are_lost(client, database_url):
    url = f"/results/{SUCCEEDED['job_id']}"
    await client.put(url, json=SUCCEEDED)  # leaves a connection in the pool
    await _terminate_other_connections(database_url)

    response = await client.get(url)

    assert response.status_code == 200


async def test_root_serves_the_ui_page(unreachable_db_client):
    response = await unreachable_db_client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>People Counter</title>" in response.text


async def test_ui_config_points_at_the_analysis_service(http_client):
    # The engine connects lazily, so this database is never reached.
    async with http_client(
        "postgresql+asyncpg://u:p@db/none",
        analysis_public_url="https://analysis.example/",
    ) as client:
        response = await client.get("/ui-config")

    assert response.status_code == 200
    assert response.json() == {"analysis_url": "https://analysis.example"}
