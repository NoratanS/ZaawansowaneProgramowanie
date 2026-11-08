import math

import numpy as np
import pytest

from analysis_service import yolox

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("shape", [(1, 2000, 3), (2000, 1, 3), (1, 1, 3)])
def test_letterbox_accepts_images_thinner_than_one_scaled_pixel(shape):
    blob, ratio = yolox.letterbox(np.zeros(shape, dtype=np.uint8))

    assert blob.shape == (1, 3, 640, 640)
    assert ratio == 640 / max(shape[:2])


def test_letterbox_converts_to_rgb_and_pads_with_gray():
    image = np.zeros((320, 640, 3), dtype=np.uint8)
    image[:, :] = (255, 0, 0)  # pure blue in BGR

    blob, ratio = yolox.letterbox(image)

    assert ratio == 1.0
    assert blob[0, :, 0, 0].tolist() == [0, 0, 255]
    assert blob[0, :, 639, 0].tolist() == [114, 114, 114]


def raw_output():
    """A fake YOLOX output: one row per anchor, 4 box + 1 objectness + 80 classes."""
    return np.zeros((1, 8400, 85), dtype=np.float32)


def test_people_keeps_persons_and_maps_boxes_back_to_the_source_image():
    output = raw_output()
    # Anchor 0 is grid cell (0, 0) at stride 8: centre (4, 4), size 32x64.
    output[0, 0, :5] = [0.5, 0.5, math.log(4), math.log(8), 0.9]
    output[0, 0, 5] = 1.0
    # Anchor 2 is cell (2, 0): the same box, less sure, so NMS drops it.
    output[0, 2, :5] = [-1.5, 0.5, math.log(4), math.log(8), 0.8]
    output[0, 2, 5] = 1.0
    # Anchor 5 looks more like a car (class 2) than a person.
    output[0, 5, :5] = [0.5, 0.5, 1.0, 1.0, 1.0]
    output[0, 5, 5] = 0.6
    output[0, 5, 7] = 0.9

    found = yolox.people(output, ratio=0.5)

    assert found == [pytest.approx((-24.0, -56.0, 64.0, 128.0, 0.9))]


def test_people_returns_nothing_below_the_score_threshold():
    output = raw_output()
    output[0, 0, :5] = [0.5, 0.5, 1.0, 1.0, 0.4]
    output[0, 0, 5] = 1.0

    assert yolox.people(output, ratio=1.0) == []
