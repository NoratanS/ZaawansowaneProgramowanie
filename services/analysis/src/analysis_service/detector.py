"""The detector seam: ``detect(image) -> list[Detection]``."""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Detection:
    """One person, in float pixels of the image; it may extend past the edges."""

    x: float
    y: float
    width: float
    height: float
    confidence: float


Detect = Callable[[np.ndarray], list[Detection]]


def detect_nobody(image: np.ndarray) -> list[Detection]:
    """Stand-in detector until the real YOLOX-S one lands (ticket 06)."""
    return []
