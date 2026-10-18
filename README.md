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

## Queues on files

A job queue stored in `src/queues_on_files/queue.csv`. Each job has a status:
`pending` → `in_progress` → `done`. A file lock stops two consumers from
taking the same job.

```bash
cd src/queues_on_files
for i in $(seq 100); do uv run python producer.py; done   # queue 100 jobs
uv run python consumer.py    # run this in several terminals
```

Each job takes 30s; an idle consumer checks the file every 5s.
