# Local development runbook

The repository-level `Makefile` is the main interface for local development. The frontend sends
requests to the FastAPI backend, so run both services to use the application.

## Prerequisites

- Node.js and npm
- [`uv`](https://docs.astral.sh/uv/) for Python and backend dependency management

## First-time setup

From the repository root, install both backend and frontend dependencies:

```sh
make setup
```

`make install` is an alias for the same command. The setup target runs `uv sync` for the backend
and `npm install` in `frontend/`.

## Run the application

Start both development servers from the repository root:

```sh
make run
```

Stop both servers with `Ctrl+C`.

To run the services separately, use two terminals:

```sh
# Terminal 1
make backend

# Terminal 2
make frontend
```

The defaults can be overridden with Make variables. For example:

```sh
make run BACKEND_PORT=8080 FRONTEND_PORT=3000
```

The available variables and their defaults are:

| Variable | Default |
| --- | --- |
| `BACKEND_HOST` | `127.0.0.1` |
| `BACKEND_PORT` | `8000` |
| `FRONTEND_HOST` | `localhost` |
| `FRONTEND_PORT` | `5173` |
| `API_BASE_URL` | `http://$(BACKEND_HOST):$(BACKEND_PORT)` |

Run `make help` to see all Make targets.

## Backend

The backend is available at:

- API: `http://127.0.0.1:8000`
- Interactive API documentation: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`

The seeded development teacher account is:

```text
Username: admin
Password: piano
```

Get an admin bearer token with:

```sh
curl -X POST http://127.0.0.1:8000/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"piano"}'
```

Send the returned `accessToken` as `Authorization: Bearer <token>` when calling `/admin/*`
endpoints. Student routes use the personal token in the URL; seeded examples include
`http://127.0.0.1:8000/s/anna`, `/s/jonas`, and `/s/mira`.

### The JWT signing secret

Admin tokens are signed with `PIANO_JWT_SECRET`. The backend resolves it while it is being
imported, before the API object is built and before the server binds a port, so a missing or
unusable secret fails immediately rather than on the first login. There are three outcomes:

- **`PIANO_JWT_SECRET` is set to a usable value** - it is used as the signing key. A usable value
  is non-blank and **at least 32 characters** long. An explicitly set secret always wins, even
  when `PIANO_DEV_MODE=1` is also set.
- **`PIANO_JWT_SECRET` is unset and `PIANO_DEV_MODE=1`** - the backend generates a random secret
  for that process and prints one line to stderr saying so. The value itself is never logged.
  Admin tokens stop working at the next restart, because the next run generates a new secret.
  This is what `make backend`, `make run`, `make test` and `uv run pytest` do, so a clean checkout
  needs no setup.
- **Neither is set** - the backend refuses to start. It prints a message to stderr naming
  `PIANO_JWT_SECRET` and both ways forward, and exits non-zero. The same refusal applies when
  `PIANO_JWT_SECRET` is set but blank, whitespace-only, or shorter than 32 characters.

The 32-character minimum is a floor against placeholder and obviously short secrets. It is not a
guarantee of entropy - generate the value from a cryptographic random source:

```sh
export PIANO_JWT_SECRET="$(uv run python -c 'import secrets; print(secrets.token_urlsafe(32))')"
make backend
```

Keep the secret out of version control. Rotating it invalidates every admin token signed with the
previous value.

The backend persists data in `./piano.db` by default. Set `PIANO_DATABASE_URL` to choose another
SQLAlchemy database URL:

```sh
PIANO_DATABASE_URL=sqlite+pysqlite:///./data/piano.db make backend
```

The database is seeded only when it is empty, so restarting the server preserves changes.

## Database migrations

The schema is owned by Alembic (`backend/alembic.ini`, `backend/migrations/`), not by
`create_all`. Starting the backend upgrades its database to the latest revision first, so in normal
local development there is nothing to run by hand.

To upgrade a database without starting the server:

```sh
make migrate
```

It reads `PIANO_DATABASE_URL` the same way `make backend` and `make test` do, so point it at the
same database the server uses:

```sh
PIANO_DATABASE_URL=sqlite+pysqlite:///./data/piano.db make migrate
```

### Writing a new revision

Change the models in `backend/db_models.py`, then generate a revision by comparing them against an
up-to-date database:

```sh
make migrate
uv run alembic -c backend/alembic.ini revision --autogenerate -m "add lesson notes"
```

Read the generated file before committing it - autogenerate is a first draft. SQLite cannot
`ALTER TABLE` for most column and constraint changes, so `env.py` sets `render_as_batch=True` and
column changes come out wrapped in `op.batch_alter_table`. Keep that wrapping.

### Upgrading a `piano.db` created before migrations existed

A `piano.db` from before this change has the tables but no `alembic_version` table, so Alembic does
not know which revision it is at. There are three ways forward.

**Just start the backend** (what most people want). `make backend` recognises a database that has
the initial schema but no version table, stamps it with the initial revision, and upgrades from
there. Your rows are left alone:

```sh
make backend
```

**Start over from a fresh seed.** The local database only ever holds demo data, so throwing it away
costs nothing. Delete it and restart - the backend recreates the schema and reseeds it:

```sh
rm piano.db
make backend
```

**Keep the data and stay on the command line.** `make migrate` on its own will fail on a
pre-Alembic database, because the initial revision tries to create tables that are already there.
Tell Alembic where the database already is, once:

```sh
uv run alembic -c backend/alembic.ini stamp head
```

After that, `make migrate` is the only command needed for every later revision.

## Frontend

With the default Make variables, the frontend is available at `http://localhost:5173`. Useful
seeded pages are:

- Home: `http://localhost:5173/`
- Admin calendar: `http://localhost:5173/admin`
- Students: `http://localhost:5173/admin/students`
- Student view: `http://localhost:5173/s/anna`

The frontend uses `http://127.0.0.1:8000` as its API base by default. The Makefile derives it from
`BACKEND_HOST` and `BACKEND_PORT`; set `API_BASE_URL` to override it when using `make`. For direct
frontend commands and production builds, set `VITE_API_BASE_URL` instead.

## Checks

Run all automated checks (backend tests, frontend linting, and a frontend production build):

```sh
make check
```

Each check is also available separately:

```sh
make test
make lint
make build
```
