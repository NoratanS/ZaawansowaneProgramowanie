"""Download an image and find the people in it.

Uses MobileNet-SSD (trained on COCO) through OpenCV's DNN module:
https://github.com/opencv/opencv/wiki/TensorFlow-Object-Detection-API
"""

import threading
import urllib.request
from pathlib import Path

import cv2
import numpy as np

MODEL_DIR = Path(__file__).parent / "model"
PERSON_CLASS = 1  # class id of "person" in COCO
MIN_CONFIDENCE = 0.5

NET = cv2.dnn.readNetFromTensorflow(
    str(MODEL_DIR / "frozen_inference_graph.pb"),
    str(MODEL_DIR / "ssd_mobilenet_v2_coco_2018_03_29.pbtxt"),
)
# The network object is not thread-safe, and FastAPI runs `def` endpoints in
# a thread pool, so only one thread may use it at a time.
NET_LOCK = threading.Lock()


def download_image(url: str) -> np.ndarray:
    # Some hosts (e.g. Wikimedia) reject requests without a User-Agent.
    request = urllib.request.Request(url, headers={"User-Agent": "api-rabbit/0.1"})
    with urllib.request.urlopen(request, timeout=10) as response:
        data = np.frombuffer(response.read(), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Not an image: {url}")
    return image


def detect_people(image: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Return one (x, y, width, height) box per person found."""
    height, width = image.shape[:2]
    blob = cv2.dnn.blobFromImage(image, size=(300, 300), swapRB=True)
    with NET_LOCK:
        NET.setInput(blob)
        # shape (1, 1, N, 7): [_, class, confidence, left, top, right, bottom]
        detections = NET.forward()[0, 0]
    boxes = []
    for _, class_id, confidence, left, top, right, bottom in detections:
        if class_id == PERSON_CLASS and confidence >= MIN_CONFIDENCE:
            x, y = int(left * width), int(top * height)
            boxes.append((x, y, int(right * width) - x, int(bottom * height) - y))
    return boxes
