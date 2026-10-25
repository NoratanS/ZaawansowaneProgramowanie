from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from analysis_service.messages import AnalysisResult

pytestmark = pytest.mark.unit

BOX = {"x": 0, "y": 0, "width": 2, "height": 2, "confidence": 0.5}
ERROR = {"code": "not_an_image", "message": "not a picture"}


def result(**fields):
    base = {
        "job_id": uuid4(),
        "image_url": "https://images.example/people.jpg",
        "model": "yolox-s",
        "requested_at": datetime.now(UTC),
        "analyzed_at": datetime.now(UTC),
    }
    return AnalysisResult(**base | fields)


def test_a_succeeded_result_has_a_count_matching_its_boxes():
    succeeded = result(status="succeeded", person_count=1, detections=[BOX])

    assert succeeded.person_count == 1


def test_a_failed_result_has_only_an_error():
    failed = result(status="failed", error=ERROR)

    assert failed.error.code == "not_an_image"


@pytest.mark.parametrize(
    "fields",
    [
        {"status": "succeeded", "person_count": 2, "detections": [BOX]},
        {"status": "succeeded", "detections": [BOX]},
        {"status": "succeeded", "person_count": 0},
        {"status": "succeeded", "person_count": 0, "detections": [], "error": ERROR},
        {"status": "failed"},
        {"status": "failed", "error": ERROR, "person_count": 0},
        {"status": "failed", "error": ERROR, "detections": []},
    ],
    ids=[
        "count-mismatch",
        "no-count",
        "no-detections",
        "succeeded-with-error",
        "failed-without-error",
        "failed-with-count",
        "failed-with-detections",
    ],
)
def test_a_result_with_the_wrong_shape_is_refused(fields):
    with pytest.raises(ValidationError):
        result(**fields)


@pytest.mark.parametrize(
    "box",
    [
        BOX | {"x": -1},
        BOX | {"width": 0},
        BOX | {"confidence": 1.5},
    ],
    ids=["negative-x", "zero-width", "confidence-over-1"],
)
def test_a_box_outside_the_rules_is_refused(box):
    with pytest.raises(ValidationError):
        result(status="succeeded", person_count=1, detections=[box])


def test_naive_timestamps_are_refused():
    with pytest.raises(ValidationError, match="analyzed_at"):
        result(status="failed", error=ERROR, analyzed_at=datetime.now())


def test_timestamps_are_stored_in_utc():
    warsaw = timezone(timedelta(hours=2))
    stamped = result(
        status="failed",
        error=ERROR,
        analyzed_at=datetime(2026, 10, 25, 14, 0, tzinfo=warsaw),
    )

    assert stamped.analyzed_at == datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
    assert stamped.analyzed_at.utcoffset() == timedelta(0)
