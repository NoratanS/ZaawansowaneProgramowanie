"""Test doubles shared by the unit and integration tests."""

from contextlib import asynccontextmanager

import cv2
import numpy as np

from analysis_service.queues import NotQueued
from analysis_service.uploads import StoredUpload


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


class FakeJobs:
    """Stands in for a work queue: records each published message and its id.

    Set ``refusing`` to make every publish raise ``NotQueued``.
    """

    def __init__(self):
        self.published = []
        self.message_ids = []
        self.refusing = False

    async def publish(self, message, message_id):
        if self.refusing:
            raise NotQueued(f"message_id={message_id} not confirmed")
        self.published.append(message)
        self.message_ids.append(message_id)


class MemoryUploadStore:
    """Stands in for the S3 Upload store: keeps each upload in a dict."""

    def __init__(self):
        self.uploads = {}  # upload_id -> (content_type, data)

    async def create_bucket_if_missing(self):
        pass

    async def put(self, upload_id, file, content_type):
        self.uploads[upload_id] = (content_type, file.read())

    @asynccontextmanager
    async def open(self, upload_id):
        if upload_id not in self.uploads:
            yield None
            return
        content_type, data = self.uploads[upload_id]

        async def chunks():
            yield data

        yield StoredUpload(content_type=content_type, length=len(data), chunks=chunks())
