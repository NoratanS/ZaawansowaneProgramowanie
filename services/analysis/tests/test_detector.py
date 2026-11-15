import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from analysis_service.messages import Box
from analysis_service.worker import yolox
from analysis_service.worker.detector import load_detector

FIXTURES = Path(__file__).parent / "fixtures"


class StubNet:
    """Stands in for the YOLOX net: ``forward`` returns a crafted raw output."""

    def __init__(self, output):
        self.output = output

    def setInput(self, blob):
        pass

    def forward(self):
        return self.output


def raw_output(people, ratio):
    """The raw YOLOX output that decodes to these ``(x, y, w, h, score)`` people.

    ``ratio`` is the letterbox scale of the image the net is run on.
    """
    rows = yolox.GRIDS.shape[1]
    output = np.zeros((1, rows, 85))
    for row, (x, y, width, height, score) in enumerate(people):
        grid_x, grid_y = yolox.GRIDS[0, row]
        stride = yolox.EXPANDED_STRIDES[0, row, 0]
        output[0, row, :4] = [
            (x + width / 2) * ratio / stride - grid_x,
            (y + height / 2) * ratio / stride - grid_y,
            np.log(width * ratio / stride),
            np.log(height * ratio / stride),
        ]
        output[0, row, 4] = 1.0  # objectness
        output[0, row, 5] = score  # class 0, person
    return output


def boxes_for(monkeypatch, *people, width=40, height=30):
    """The boxes ``detect`` returns on a blank image whose net finds ``people``."""
    ratio = min(yolox.INPUT_SIZE / height, yolox.INPUT_SIZE / width)
    net = StubNet(raw_output(people, ratio))
    monkeypatch.setattr(cv2.dnn, "readNet", lambda path: net)
    detect = load_detector("yolox.onnx")

    boxes = detect(np.zeros((height, width, 3), dtype=np.uint8))

    assert all(isinstance(box, Box) for box in boxes)
    return [box.model_dump() for box in boxes]


@pytest.mark.unit
def test_boxes_are_clipped_to_the_image_and_rounded(monkeypatch):
    boxes = boxes_for(
        monkeypatch,
        # Sticks out left and bottom: clipped to the image, then rounded.
        (-5.4, 2.6, 20.0, 40.0, 0.9),
        (10.2, 5.0, 8.6, 10.4, 0.6),
    )

    assert boxes == [
        {"x": 0, "y": 3, "width": 15, "height": 27, "confidence": 0.9},
        {"x": 10, "y": 5, "width": 9, "height": 10, "confidence": 0.6},
    ]


OUTSIDE = {
    "left": (-10.0, 5.0, 5.0, 5.0, 0.9),
    "right": (50.0, 5.0, 5.0, 5.0, 0.9),
    "above": (5.0, -20.0, 5.0, 10.0, 0.9),
    "below": (5.0, 31.0, 5.0, 5.0, 0.9),
    # Inside, but under half a pixel wide: rounds to zero width.
    "sliver": (10.2, 5.0, 0.2, 5.0, 0.9),
}


@pytest.mark.unit
@pytest.mark.parametrize("outside", OUTSIDE.values(), ids=OUTSIDE.keys())
def test_boxes_clipped_away_entirely_are_dropped(monkeypatch, outside):
    kept = (1.0, 1.0, 4.0, 4.0, 0.8)

    assert boxes_for(monkeypatch, outside, kept) == [
        {"x": 1, "y": 1, "width": 4, "height": 4, "confidence": 0.8}
    ]


@pytest.mark.unit
def test_a_box_bigger_than_the_image_is_clipped_to_the_whole_image(monkeypatch):
    huge = (-5.0, -5.0, 100.0, 100.0, 0.7)

    assert boxes_for(monkeypatch, huge) == [
        {"x": 0, "y": 0, "width": 40, "height": 30, "confidence": 0.7}
    ]


@pytest.mark.unit
def test_no_people_is_no_boxes(monkeypatch):
    assert boxes_for(monkeypatch) == []


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
    for box in found:
        assert isinstance(box, Box)
        assert 0.0 < box.confidence <= 1.0
        # Boxes are clipped to the photo's pixels, not the 640x640 model input.
        assert box.x + box.width <= width and box.y + box.height <= height
