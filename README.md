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

## Tests

The repo is a uv workspace with two services in `services/`. Run one test tier
at a time from the repo root:

```bash
uv run pytest -m unit          # pure logic, no I/O
uv run pytest -m integration   # real Postgres + RabbitMQ (needs Docker)
uv run pytest -m e2e           # full compose stack
uv run pytest -m model         # the real YOLOX model on a fixture photo
```

Nothing needs to be started first. Integration tests start throwaway
`postgres:18` and `rabbitmq:4.3-management` containers on random ports and
remove them when the run ends.
