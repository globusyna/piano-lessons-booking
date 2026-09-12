For backand us uv for dependencies management:

Commands

- `uv sync` - install dependencies
- `uv add <PACKAGE NAME>` - add new package
- `uv run python <PYTHON FILE>` - install dependencies
- `uv run pytest` - the whole suite
- `uv run pytest tests/test_home.py` - one test file

Rules

- Dependencies are added in `pyproject.toml`. Do not add one without
  asking

Documents

- `_docs/process.md` - how work is organized
- Before writing tests, read `_docs/testing-guidelines.md`

Version control

- rgularly commit code to git