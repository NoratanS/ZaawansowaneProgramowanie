import pytest

from analysis_service.queues import JOBS, RESULTS, QueueConfig, queue_arguments

pytestmark = pytest.mark.unit


def test_jobs_queue_arguments_match_the_spec():
    assert queue_arguments(JOBS) == {
        "x-delayed-retry-type": "failed",
        "x-delayed-retry-min": 2000,
        "x-delayed-retry-max": 30000,
        "x-delivery-limit": 3,
        "x-dead-letter-exchange": "analysis-jobs.dlx",
        "x-dead-letter-strategy": "at-least-once",
        "x-overflow": "reject-publish",
    }


def test_results_queue_follows_the_spec():
    assert RESULTS == QueueConfig(
        name="analysis-results",
        retry_min_seconds=2,
        retry_max_seconds=60,
        delivery_limit=20,
    )


def test_retry_min_must_not_exceed_retry_max():
    with pytest.raises(ValueError, match="must not exceed"):
        QueueConfig(
            name="analysis-jobs",
            retry_min_seconds=60,
            retry_max_seconds=30,
            delivery_limit=3,
        )


def test_fractional_seconds_become_whole_milliseconds():
    config = QueueConfig(
        name="analysis-results",
        retry_min_seconds=0.05,
        retry_max_seconds=0.2,
        delivery_limit=20,
    )

    arguments = queue_arguments(config)

    assert arguments["x-delayed-retry-min"] == 50
    assert arguments["x-delayed-retry-max"] == 200
    assert arguments["x-dead-letter-exchange"] == "analysis-results.dlx"


def test_dead_letter_names_derive_from_the_queue_name():
    assert JOBS.dlx == "analysis-jobs.dlx"
    assert JOBS.dlq == "analysis-jobs.dlq"
