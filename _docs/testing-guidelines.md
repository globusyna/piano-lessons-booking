- `uv run pytest` for the suite, `uv run pytest tests/test_admin.py` for one file
- `make check` before handing work over - it runs the suite, the frontend
  lint and the frontend build
- Write a test when a bug is found, reproducing it before fixing it

What to test

- Go through the HTTP endpoint with the `client` fixture, not by calling
  store methods. `tests/test_database.py` is the exception: persistence
  and schema are tested against `DatabaseStore` directly
- One test per user-visible behaviour, named for the behaviour
- Assert the error code, not only the status:
  `response.json()["error"]["code"] == "INVALID_TOKEN"`
- Cover the awkward cases the acceptance criteria name, not just the
  happy path

Shape

- Arrange and act first, then the assertions in a block at the end
- Annotate the signature and return `-> None`
- No mocks. The tests run against the real store on in-memory SQLite

Fixtures

- `client`, `admin_headers` and the autouse `reset_store` live in
  `tests/conftest.py`
- conftest pins `PIANO_DATABASE_URL` to in-memory SQLite before importing
  the backend. Do not import backend modules above that line, and never
  let a test touch `piano.db`
- For persistence, build a `DatabaseStore` on a `tmp_path` URL and
  dispose its engine at the end

Seed data

- The suite leans on the seeded studio - `/s/anna` is Anna Lie, Jonas
  Berg carries the invoice alert. Using it is fine
- If new behaviour needs its own data, create it through the admin
  endpoints rather than extending the seed

Time

- Derive dates from `datetime.now(STUDIO_TZ)`, never hard-code one. The
  suite has to pass next year
- There is no clock control until #32 lands. Do not sleep and do not
  depend on a particular time of day - say so on the issue instead

Frontend

- No frontend tests exist yet (#31). `make lint` and `make build` are the
  only checks there, so do not report frontend behaviour as covered
