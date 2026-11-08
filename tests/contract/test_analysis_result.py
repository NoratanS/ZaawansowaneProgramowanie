"""Both services model the Analysis Result; these tests catch drift between them.

The Courier ``PUT``s the Worker's JSON unchanged, so each model must accept
what the other one serializes.
"""

from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from analysis_service.messages import AnalysisResult as WorkerResult
from results_service.models import AnalysisResult as StoredResult

pytestmark = pytest.mark.unit

WARSAW = timezone(timedelta(hours=1))


def fields():
    return {
        "job_id": uuid4(),
        "image_url": "https://images.example/people.jpg",
        "model": "yolox-s",
        "requested_at": datetime(2026, 11, 8, 12, 0, tzinfo=UTC),
        # Non-UTC on purpose: both sides must still agree on the instant.
        "analyzed_at": datetime(2026, 11, 8, 13, 0, 2, tzinfo=WARSAW),
        "error": None,
    }


BOXES = [
    {"x": 0, "y": 3, "width": 15, "height": 27, "confidence": 0.9},
    {"x": 10, "y": 5, "width": 9, "height": 10, "confidence": 1.0},
]
OUTCOMES = {
    "succeeded": {"status": "succeeded", "person_count": 2, "detections": BOXES},
    "succeeded-empty": {"status": "succeeded", "person_count": 0, "detections": []},
    "failed": {
        "status": "failed",
        "person_count": None,
        "detections": None,
        "error": {"code": "not_an_image", "message": "not a picture"},
    },
    "forbidden": {
        "status": "failed",
        "person_count": None,
        "detections": None,
        "error": {"code": "image_url_forbidden", "message": "internal address"},
    },
}


@pytest.mark.parametrize("outcome", OUTCOMES.values(), ids=OUTCOMES.keys())
@pytest.mark.parametrize(
    ("source", "target"),
    [(WorkerResult, StoredResult), (StoredResult, WorkerResult)],
    ids=["worker-to-results-service", "results-service-to-worker"],
)
def test_each_model_accepts_the_others_json(source, target, outcome):
    built = source(**fields() | outcome)

    parsed = target.model_validate_json(built.model_dump_json())

    # Aware datetimes compare by instant, so a UTC-normalized copy still matches.
    assert parsed.model_dump() == built.model_dump()
