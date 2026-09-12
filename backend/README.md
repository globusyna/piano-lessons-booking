# Backend

The backend is a FastAPI application backed by SQLAlchemy. It uses a persistent SQLite database
at `./piano.db` by default and seeds it on first use.

Start it from the repository root:

```sh
uv sync
uv run uvicorn backend.main:app --reload
```

API documentation is available at `http://127.0.0.1:8000/docs`. The development teacher login is
`admin` / `piano`. Exchange it at `POST /auth/token`, then send the returned JWT as
`Authorization: Bearer <token>` on `/admin/*` requests. Set `PIANO_JWT_SECRET` outside local
development so issued tokens use an application-specific signing key.

Student endpoints use the personal token in their URL. Seeded examples include `/s/anna`,
`/s/jonas`, and `/s/mira`.

Set `PIANO_DATABASE_URL` to any SQLAlchemy database URL before starting the server to use another
database. For example:

```sh
PIANO_DATABASE_URL=sqlite+pysqlite:///./data/piano.db \
  uv run uvicorn backend.main:app --reload
```

The models and store use SQLAlchemy's portable types and query APIs. Adding PostgreSQL later only
requires its database driver and a PostgreSQL URL; database-specific engine options are isolated
in `backend/database.py`.

Run the tests with:

```sh
uv run pytest
```
