# Backend

The backend is a FastAPI application with a seeded, in-memory data store. State resets whenever
the process restarts.

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

Run the tests with:

```sh
uv run pytest
```
