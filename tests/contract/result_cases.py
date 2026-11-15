"""The shared Analysis Result cases in ``cases/``, for the tests of both services.

Each case is one JSON file: a Result ``body`` and whether each side accepts it.
The services' tests read the files through this module, never through each
other's code (ADR-0001).
"""

import json
from pathlib import Path
from typing import Literal, NamedTuple

CASES = Path(__file__).parent / "cases"

Outcome = Literal["accept", "reject"]


class ResultCase(NamedTuple):
    name: str
    body: dict
    analysis_service: Outcome
    results_service: Outcome


def load(name: str) -> ResultCase:
    """The case in ``cases/<name>.json``, with a fresh copy of its body."""
    case = json.loads((CASES / f"{name}.json").read_text())
    expected = case["expected"]
    return ResultCase(
        name, case["body"], expected["analysis_service"], expected["results_service"]
    )


def all_cases() -> list[ResultCase]:
    return [load(path.stem) for path in sorted(CASES.glob("*.json"))]
