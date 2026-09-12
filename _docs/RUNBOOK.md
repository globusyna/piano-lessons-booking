# Local development runbook

The repository-level `Makefile` is the main interface for local development. The frontend is
currently fixture-backed, so it does not yet send requests to the backend; running both services
still gives you the UI and API development environments side by side.

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

For anything beyond local development, set a private JWT signing secret before starting the API:

```sh
export PIANO_JWT_SECRET='replace-with-a-long-random-secret'
make backend
```

The backend uses an in-memory store. Restarting it discards changes and restores the seed data.

## Frontend

With the default Make variables, the frontend is available at `http://localhost:5173`. Useful
seeded pages are:

- Home: `http://localhost:5173/`
- Admin calendar: `http://localhost:5173/admin`
- Students: `http://localhost:5173/admin/students`
- Student view: `http://localhost:5173/s/anna`

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
