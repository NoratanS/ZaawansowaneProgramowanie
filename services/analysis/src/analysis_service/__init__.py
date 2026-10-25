"""Analysis Service, Worker and Courier."""

import os

# Cap decoded image size: a small compressed file can declare huge dimensions.
# OpenCV reads this once, when cv2 is first imported, so it must be set here.
# Over the cap, cv2.imdecode raises before allocating the pixels.
os.environ.setdefault("OPENCV_IO_MAX_IMAGE_PIXELS", str(50_000_000))
