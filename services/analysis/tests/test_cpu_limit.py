import pytest

from analysis_service.worker import cpu_limit

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("cpu_max", "host_cpus", "expected"),
    [
        ("200000 100000\n", 8, 2),  # --cpus=2
        ("150000 100000\n", 8, 2),  # --cpus=1.5 rounds up, never to 0
        ("50000 100000\n", 8, 1),  # --cpus=0.5
        ("1600000 100000\n", 8, 8),  # quota above the host is capped
        ("max 100000\n", 8, 8),  # no quota
        ("", 4, 4),  # no cgroup v2 file
        ("garbage\n", 4, 4),  # unexpected formats fall back to the host
    ],
)
def test_threads_follow_the_container_cpu_quota(cpu_max, host_cpus, expected):
    assert cpu_limit(cpu_max, host_cpus) == expected
