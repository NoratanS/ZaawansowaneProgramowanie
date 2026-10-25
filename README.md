## Setup

```bash
uv sync
uv run pre-commit install
```

`uv sync` installs the project and dev tools. `pre-commit install` turns on
the git hook that checks your code on every commit (run it once per clone).

## Code style

Code is formatted with [Black](https://black.readthedocs
with [pycodestyle](https://pycodestyle.pycqa.org/) (line length 88).
The same checks run in CI on every push to `main`/`dev`

Run the checks manually:

```bash
uv run black .               # format code
uv run pycodestyle .         # check style
uv run pre-commit run --all-files   # run all hooks on e
```

## People detection API with RabbitMQ

`GET /analyze_img?url=...` puts a job `{id, url}` on a RabbitMQ queue and
returns its `id`. Consumers take jobs off the queue, count the people with
MobileNet-SSD (OpenCV DNN) and save the image with boxes as
`results/{id}-{number-of-people}.{extension}`. `GET /check?id=...` reads that
file name and returns `pending` or the number of people.
`GET /analyze_img_sync?url=...` is the first version, which analyses the
image inside the request.

```bash
cd src/api_rabbit
mkdir -p model && cd model
curl -L https://storage.googleapis.com/download.tensorflow.org/models/object_detection/ssd_mobilenet_v2_coco_2018_03_29.tar.gz \
  | tar xz --strip-components=1 ssd_mobilenet_v2_coco_2018_03_29/frozen_inference_graph.pb
curl -LO https://raw.githubusercontent.com/opencv/opencv_extra/4.x/testdata/dnn/ssd_mobilenet_v2_coco_2018_03_29.pbtxt
cd ..

docker compose up -d          # RabbitMQ, web UI on http://localhost:15672
uv run python main.py         # API on http://127.0.0.1:5000
uv run python consumer.py     # run this in as many terminals as you need

uv run python load_test.py analyze_img_sync <image_url>   # 10/20/30 requests at once
uv run python load_test.py analyze_img <image_url>
```

Load test results with a 640x480 photo (one request alone takes ~0.3s):

| Requests at once | `/analyze_img_sync` slowest | `/analyze_img` slowest |
|---|---|---|
| 10 | 1.64s | 0.18s |
| 20 | 3.15s | 0.26s |
| 30 | 5.07s | 0.66s |

The synchronous API does not freeze: FastAPI runs `def` endpoints in a
thread pool, so `/check` still answered in 0.02s during the 30-request test.
But the analyses share the CPU and the model, so each extra request makes all
the others wait longer. With bigger images or a heavier model, clients
start hitting timeouts. With the queue, the API only publishes a message and
answers right away. The work waits in RabbitMQ until a consumer is free, and
more consumers can be started to clear it faster.
