import pytest

from results_service import main


@pytest.mark.unit
def test_package_imports():
    assert callable(main.main)
