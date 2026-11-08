import os
from pathlib import Path

import cv2
import pytest

from analysis_service.detector import load_detector

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def detect():
    model_path = os.environ.get("MODEL_PATH", "")
    if not Path(model_path).is_file():
        pytest.skip("set MODEL_PATH to object_detection_yolox_2022nov.onnx")
    return load_detector(model_path)


@pytest.mark.model
def test_counts_the_people_in_a_group_photo(detect):
    # COCO val2017 #1000: about 12 people playing tennis, several overlapping.
    image = cv2.imread(str(FIXTURES / "tennis-group.jpg"))

    found = detect(image)

    assert 9 <= len(found) <= 15
    height, width = image.shape[:2]
    for d in found:
        assert 0.0 < d.confidence <= 1.0
        assert d.width > 0 and d.height > 0
        # Boxes are in the photo's pixels, not the 640x640 model input.
        assert -d.width < d.x < width and -d.height < d.y < height
