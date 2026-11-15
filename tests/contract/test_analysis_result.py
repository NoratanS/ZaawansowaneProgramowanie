"""Both services model the Analysis Result; these tests catch drift between them.

The Courier ``PUT``s the Worker's JSON unchanged, so each model must accept
what the other one serializes. Every case in ``cases/`` says what each side
should do with its body.
"""

import json
from typing import get_args

import pytest
from pydantic import ValidationError

from analysis_service import messages as worker
from result_cases import all_cases
from results_service import models as results_service

pytestmark = pytest.mark.unit

MODELS = {
    "worker": worker.AnalysisResult,
    "results_service": results_service.AnalysisResult,
}
CASES = all_cases()
ACCEPTED_BY_BOTH = [
    case for case in CASES if case.worker == case.results_service == "accept"
]


def ids(case):
    return case.name


@pytest.mark.parametrize("side", MODELS)
@pytest.mark.parametrize("case", CASES, ids=ids)
def test_each_side_accepts_or_rejects_each_case_as_expected(case, side):
    model = MODELS[side]
    body = json.dumps(case.body)

    if getattr(case, side) == "accept":
        model.model_validate_json(body)
    else:
        with pytest.raises(ValidationError):
            model.model_validate_json(body)


@pytest.mark.parametrize("case", ACCEPTED_BY_BOTH, ids=ids)
@pytest.mark.parametrize(
    ("source", "target"),
    [
        (worker.AnalysisResult, results_service.AnalysisResult),
        (results_service.AnalysisResult, worker.AnalysisResult),
    ],
    ids=["worker-to-results-service", "results-service-to-worker"],
)
def test_each_model_accepts_the_others_json(source, target, case):
    built = source.model_validate_json(json.dumps(case.body))

    parsed = target.model_validate_json(built.model_dump_json())

    # Aware datetimes compare by instant, so a UTC-normalized copy still matches.
    assert parsed.model_dump() == built.model_dump()


def test_both_sides_have_the_same_error_codes():
    assert get_args(worker.ErrorCode) == get_args(results_service.ErrorCode)


@pytest.mark.parametrize(
    "codes",
    [get_args(worker.ErrorCode), get_args(results_service.ErrorCode)],
    ids=["worker", "results-service"],
)
def test_every_error_code_has_a_failed_case_both_sides_accept(codes):
    covered = {
        case.body["error"]["code"] for case in ACCEPTED_BY_BOTH if case.body["error"]
    }

    assert set(codes) <= covered
