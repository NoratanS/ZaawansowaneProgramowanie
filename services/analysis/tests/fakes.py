"""Test doubles shared by the Worker's unit and integration tests."""

import cv2
import numpy as np


def png(width, height):
    ok, encoded = cv2.imencode(".png", np.zeros((height, width, 3), dtype=np.uint8))
    assert ok
    return encoded.tobytes()


class FakeDetector:
    """Stands in for YOLOX: returns canned detections and records its calls."""

    def __init__(self, detections=(), error=None):
        self.detections = list(detections)
        self.error = error
        self.images = []

    def __call__(self, image):
        self.images.append(image)
        if self.error is not None:
            raise self.error
        return self.detections
