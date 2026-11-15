from uuid import UUID

import pytest

from analysis_service.images import ImageFailure
from analysis_service.uploads import upload_id_in, url_for

pytestmark = pytest.mark.unit

BASE = "http://analysis.example/uploads"
UPLOAD_ID = UUID("0b6f3c1e-8a4d-4f2b-9c7e-1d2a3b4c5d6e")


def test_an_upload_url_names_its_upload():
    url = url_for(UPLOAD_ID, BASE)

    assert url == "http://analysis.example/uploads/0b6f3c1e-8a4d-4f2b-9c7e-1d2a3b4c5d6e"
    assert upload_id_in(url, BASE) == UPLOAD_ID


def test_a_trailing_slash_in_the_base_url_changes_nothing():
    url = f"{BASE}/{UPLOAD_ID}"

    assert url_for(UPLOAD_ID, BASE + "/") == url
    assert upload_id_in(url, BASE + "/") == UPLOAD_ID


def test_a_url_on_another_host_is_not_an_upload():
    url = f"http://images.example/uploads/{UPLOAD_ID}"

    assert upload_id_in(url, BASE) is None


@pytest.mark.parametrize(
    "url",
    [f"{BASE}/not-an-id", f"{BASE}/{UPLOAD_ID}/extra"],
    ids=["non-uuid", "extra-segment"],
)
def test_an_uploads_url_that_names_no_upload_is_unreachable(url):
    with pytest.raises(ImageFailure) as failure:
        upload_id_in(url, BASE)

    assert failure.value.code == "image_unreachable"
