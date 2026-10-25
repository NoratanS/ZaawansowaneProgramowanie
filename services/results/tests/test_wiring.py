import pytest

import results_service


@pytest.mark.unit
def test_package_imports():
    assert results_service.__name__ == "results_service"
