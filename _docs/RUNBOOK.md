# Local development runbook

Run the frontend and backend in separate terminals from the repository root. The frontend is
currently fixture-backed, so it does not yet send requests to the backend; running both gives you
the UI and API development environments side by side.

## Prerequisites

- Node.js and npm
- [`uv`](https://docs.astral.sh/uv/) for Python and backend dependency management

## First-time setup

Install the backend dependencies from the repository root:

```sh
uv sync
```

Install the frontend dependencies:

```sh
cd frontend
npm install
cd ..
```

## Start the backend

In the first terminal, from the repository root:

```sh
uv run uvicorn backend.main:app --reload
```

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
uv run uvicorn backend.main:app --reload
```

The backend uses an in-memory store. Restarting it discards changes and restores the seed data.

## Start the frontend

In a second terminal, from the repository root:

```sh
cd frontend
npm run dev
```

Open the local URL printed by Vite. It is normally `http://localhost:5173`. Useful seeded pages are:

- Home: `http://localhost:5173/`
- Admin calendar: `http://localhost:5173/admin`
- Students: `http://localhost:5173/admin/students`
- Student view: `http://localhost:5173/s/anna`

If Vite selects another port, use the URL it prints in the terminal.

## Checks

Run all backend tests from the repository root:

```sh
uv run pytest
```

Run frontend linting and a production build:

```sh
cd frontend
npm run lint
npm run build
```

Stop either development server with `Ctrl+C` in its terminal.
