"""The detector seam: ``detect(image) -> list[Detection]``."""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from os import PathLike

import cv2
import numpy as np

from analysis_service import yolox


@dataclass(frozen=True)
class Detection:
    """One person, in float pixels of the image; it may extend past the edges."""

    x: float
    y: float
    width: float
    height: float
    confidence: float


Detect = Callable[[np.ndarray], list[Detection]]


def load_detector(model_path: str | PathLike[str]) -> Detect:
    """Load YOLOX-S once; the returned ``detect`` reuses it for every image."""
    net = cv2.dnn.readNet(str(model_path))
    # One net can't run two forward passes at once.
    lock = threading.Lock()

    def detect(image: np.ndarray) -> list[Detection]:
        blob, ratio = yolox.letterbox(image)
        with lock:
            net.setInput(blob)
            output = net.forward()
        return [
            Detection(x, y, width, height, score)
            for x, y, width, height, score in yolox.people(output, ratio)
        ]

    return detect
