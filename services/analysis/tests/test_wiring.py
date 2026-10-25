import pytest

import analysis_service


@pytest.mark.unit
def test_package_imports():
    assert analysis_service.__name__ == "analysis_service"


@pytest.mark.model
def test_model_tier_is_wired():
    # Placeholder until the real detector lands (ticket 06).
    assert True
