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

  Version control

  - For every substantial new task that changes files, create a dedicated branch before editing. Use the name `codex/<short-task-name>`.
  - Check `git status` first. Never include or overwrite unrelated existing changes.
  - Commit after each coherent milestone using a descriptive commit message, and ensure all completed work is committed before
  finishing.
  - Do not create branches or commits for read-only tasks such as explanations, reviews, or diagnostics.
  - If uncommitted changes make creating the branch unsafe, ask the user how to proceed.