from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from analysis_service.messages import AnalysisResult
import result_cases

pytestmark = pytest.mark.unit


def result(case, **changes):
    return AnalysisResult.model_validate(result_cases.load(case).body | changes)


def test_a_succeeded_result_has_a_count_matching_its_boxes():
    succeeded = result("succeeded-with-boxes")

    assert succeeded.person_count == 2


def test_a_failed_result_has_only_an_error():
    failed = result("failed-not-an-image")

    assert failed.error.code == "not_an_image"


@pytest.mark.parametrize(
    "case",
    [
        "count-differs-from-detections",
        "succeeded-without-a-count",
        "succeeded-without-detections",
        "succeeded-with-an-error",
        "failed-without-an-error",
        "failed-with-a-count",
        "failed-with-detections",
    ],
)
def test_a_result_with_the_wrong_shape_is_refused(case):
    with pytest.raises(ValidationError):
        result(case)


@pytest.mark.parametrize("case", ["negative-x", "zero-width", "confidence-above-1"])
def test_a_box_outside_the_rules_is_refused(case):
    with pytest.raises(ValidationError):
        result(case)


def test_naive_timestamps_are_refused():
    with pytest.raises(ValidationError, match="analyzed_at"):
        result("failed-not-an-image", analyzed_at=datetime.now())


def test_timestamps_are_stored_in_utc():
    warsaw = timezone(timedelta(hours=2))
    stamped = result(
        "failed-not-an-image",
        analyzed_at=datetime(2026, 10, 25, 14, 0, tzinfo=warsaw),
    )

    assert stamped.analyzed_at == datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
    assert stamped.analyzed_at.utcoffset() == timedelta(0)
