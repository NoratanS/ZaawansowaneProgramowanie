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
