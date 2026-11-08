from pathlib import Path
from uuid import uuid4

import pytest

pytestmark = pytest.mark.e2e

FIXTURES = Path(__file__).parent / "fixtures"


def test_a_photo_of_people_gets_a_succeeded_analysis_result(
    submit, wait_for_result, results_url
):
    response = submit("tennis-group.jpg")

    accepted = response.json()
    expected_url = f"{results_url}/results/{accepted['job_id']}"
    assert accepted["result_url"] == expected_url
    assert response.headers["Location"] == expected_url

    result = wait_for_result(accepted["result_url"])
    assert result["status"] == "succeeded"
    assert result["model"] == "yolox-s"
    # Same photo as the model test; the real detector, so a range.
    assert 9 <= result["person_count"] <= 15
    assert len(result["detections"]) == result["person_count"]


@pytest.mark.parametrize(
    "fixture, code",
    [
        ("no-such-file.jpg", "image_unreachable"),  # nginx answers 404
        ("not-an-image.txt", "not_an_image"),
    ],
)
def test_an_image_that_cant_be_analyzed_gets_a_failed_analysis_result(
    submit, wait_for_result, fixture, code
):
    accepted = submit(fixture).json()

    result = wait_for_result(accepted["result_url"])
    assert result["status"] == "failed"
    assert result["error"]["code"] == code
    assert result["person_count"] is None
    assert result["detections"] is None


def test_post_analyses_without_a_token_is_401(http, analysis_url, images_url):
    response = http.post(
        f"{analysis_url}/analyses",
        json={"image_url": f"{images_url}/tennis-group.jpg"},
    )

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_post_analyses_with_a_courier_token_is_401(
    http, e2e_token, analysis_url, images_url
):
    response = http.post(
        f"{analysis_url}/analyses",
        json={"image_url": f"{images_url}/tennis-group.jpg"},
        headers={"Authorization": f"Bearer {e2e_token('results-service')}"},
    )

    assert response.status_code == 401


def test_put_results_with_a_client_token_is_401(
    http, client_token, results_url, images_url
):
    job_id = str(uuid4())
    result = {
        "job_id": job_id,
        "image_url": f"{images_url}/tennis-group.jpg",
        "status": "succeeded",
        "person_count": 0,
        "detections": [],
        "error": None,
        "model": "yolox-s",
        "requested_at": "2026-11-08T12:00:00Z",
        "analyzed_at": "2026-11-08T12:00:01Z",
    }

    response = http.put(
        f"{results_url}/results/{job_id}",
        json=result,
        headers={"Authorization": f"Bearer {client_token}"},
    )

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert http.get(f"{results_url}/results/{job_id}").status_code == 404


def test_delivery_survives_a_results_service_outage(
    docker_compose, submit, wait_for_result, wait_for_log
):
    docker_compose("stop", "results")
    try:
        jobs = [submit("tennis-group.jpg").json() for _ in range(3)]
        # Proof the outage was hit: the Courier tried each and is retrying.
        wait_for_log("courier", *(f"job_id={job['job_id']} retrying" for job in jobs))
    finally:
        docker_compose("start", "results")

    for job in jobs:
        assert wait_for_result(job["result_url"])["status"] == "succeeded"


def test_the_listing_contains_submitted_analysis_results(
    http, submit, wait_for_result, results_url
):
    fixtures = ("tennis-group.jpg", "not-an-image.txt")
    jobs = [submit(fixture).json() for fixture in fixtures]
    for job in jobs:
        wait_for_result(job["result_url"])

    response = http.get(f"{results_url}/results", params={"limit": 200})

    assert response.status_code == 200
    listed = {result["job_id"] for result in response.json()}
    assert {job["job_id"] for job in jobs} <= listed


def test_uploaded_photos_get_analysis_results(
    http, client_token, analysis_url, wait_for_result
):
    uploads = [
        ("tennis-group.jpg", "image/jpeg"),
        ("not-an-image.txt", "text/plain"),
    ]
    files = [
        ("files", (name, (FIXTURES / name).read_bytes(), content_type))
        for name, content_type in uploads
    ]

    response = http.post(
        f"{analysis_url}/uploads",
        files=files,
        headers={"Authorization": f"Bearer {client_token}"},
    )

    assert response.status_code == 202, response.text
    photo, text = response.json()
    assert [photo["filename"], text["filename"]] == [name for name, _ in uploads]

    succeeded = wait_for_result(photo["result_url"])
    assert succeeded["status"] == "succeeded"
    assert 9 <= succeeded["person_count"] <= 15
    # The browser loads the photo from the Result's image_url to draw boxes.
    served = http.get(succeeded["image_url"])
    assert served.status_code == 200
    assert served.headers["Content-Type"] == "image/jpeg"
    assert served.content == (FIXTURES / "tennis-group.jpg").read_bytes()

    failed = wait_for_result(text["result_url"])
    assert failed["status"] == "failed"
    assert failed["error"]["code"] == "not_an_image"
