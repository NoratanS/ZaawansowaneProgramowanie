"""YOLOX-S pre- and post-processing, vendored from the OpenCV Model Zoo.

Adapted from ``models/object_detection_yolox/yolox.py`` and ``demo.py`` in
https://github.com/opencv/opencv_zoo, Copyright the OpenCV Zoo contributors,
licensed under the Apache License, Version 2.0
(http://www.apache.org/licenses/LICENSE-2.0).

Changes from the original: the class became functions, only COCO class 0
(person) is kept, the boxes are mapped back to the source image, and very thin
images are letterboxed to at least one pixel.
"""

import cv2
import numpy as np

INPUT_SIZE = 640
STRIDES = (8, 16, 32)
PERSON = 0
SCORE_THRESHOLD = 0.5
NMS_THRESHOLD = 0.5


def letterbox(image: np.ndarray) -> tuple[np.ndarray, float]:
    """Scale a BGR image into a gray 640x640 RGB canvas; return the NCHW blob."""
    ratio = min(INPUT_SIZE / image.shape[0], INPUT_SIZE / image.shape[1])
    # At least one pixel, or cv2.resize fails on very thin images.
    width = max(1, int(image.shape[1] * ratio))
    height = max(1, int(image.shape[0] * ratio))
    padded = np.full((INPUT_SIZE, INPUT_SIZE, 3), 114, dtype=np.uint8)
    padded[:height, :width] = cv2.resize(
        image, (width, height), interpolation=cv2.INTER_LINEAR
    )
    return cv2.dnn.blobFromImage(padded, swapRB=True), ratio


def _anchors() -> tuple[np.ndarray, np.ndarray]:
    grids = []
    expanded_strides = []
    for stride in STRIDES:
        size = INPUT_SIZE // stride
        xv, yv = np.meshgrid(np.arange(size), np.arange(size))
        grid = np.stack((xv, yv), 2).reshape(1, -1, 2)
        grids.append(grid)
        expanded_strides.append(np.full((*grid.shape[:2], 1), stride))
    return np.concatenate(grids, 1), np.concatenate(expanded_strides, 1)


GRIDS, EXPANDED_STRIDES = _anchors()


def people(
    output: np.ndarray, ratio: float
) -> list[tuple[float, float, float, float, float]]:
    """Decode the raw output into ``(x, y, width, height, score)`` people boxes."""
    dets = output[0].copy()
    dets[:, :2] = (dets[:, :2] + GRIDS) * EXPANDED_STRIDES
    dets[:, 2:4] = np.exp(dets[:, 2:4]) * EXPANDED_STRIDES

    boxes = np.empty_like(dets[:, :4])
    boxes[:, 0] = dets[:, 0] - dets[:, 2] / 2.0
    boxes[:, 1] = dets[:, 1] - dets[:, 3] / 2.0
    boxes[:, 2:4] = dets[:, 2:4]
    boxes /= ratio

    # A box is a person only if "person" is its best class, as in the Zoo,
    # which runs per-class NMS over every class.
    scores = dets[:, 4:5] * dets[:, 5:]
    best = np.argmax(scores, axis=1)
    best_scores = scores[np.arange(len(scores)), best]
    candidates = np.flatnonzero((best == PERSON) & (best_scores >= SCORE_THRESHOLD))
    keep = cv2.dnn.NMSBoxes(
        boxes[candidates].tolist(),
        best_scores[candidates].tolist(),
        SCORE_THRESHOLD,
        NMS_THRESHOLD,
    )
    return [
        (*map(float, boxes[i]), float(best_scores[i]))
        for i in candidates[np.asarray(keep, dtype=int).reshape(-1)]
    ]
