import importlib

import pytest


@pytest.mark.unit
@pytest.mark.parametrize(
    "module",
    [
        "analysis_service.api.main",
        "analysis_service.worker.main",
        "analysis_service.courier.main",
    ],
)
def test_package_imports(module):
    assert callable(importlib.import_module(module).main)


@pytest.mark.model
def test_model_tier_is_wired():
    # Placeholder until the real detector lands (ticket 06).
    assert True
