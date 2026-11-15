"""The detector seam: ``detect(image) -> list[Box]``."""

import threading
from collections.abc import Callable
from os import PathLike

import cv2
import numpy as np

from analysis_service.messages import Box
from analysis_service.worker import yolox

Detect = Callable[[np.ndarray], list[Box]]


def load_detector(model_path: str | PathLike[str]) -> Detect:
    """Load YOLOX-S once; the returned ``detect`` reuses it for every image."""
    net = cv2.dnn.readNet(str(model_path))
    # One net can't run two forward passes at once.
    lock = threading.Lock()

    def detect(image: np.ndarray) -> list[Box]:
        """Clip each detection to the image and round it; drop it if nothing is left."""
        blob, ratio = yolox.letterbox(image)
        with lock:
            net.setInput(blob)
            output = net.forward()
        height, width = image.shape[:2]

        def clip(value: float, limit: int) -> int:
            return round(min(max(value, 0), limit))

        boxes = []
        for x, y, w, h, score in yolox.people(output, ratio):
            left, top = clip(x, width), clip(y, height)
            right, bottom = clip(x + w, width), clip(y + h, height)
            if right > left and bottom > top:
                boxes.append(
                    Box(
                        x=left,
                        y=top,
                        width=right - left,
                        height=bottom - top,
                        confidence=score,
                    )
                )
        return boxes

    return detect
