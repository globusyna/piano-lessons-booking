"""Alembic environment for the piano lessons backend.

Two things here are load-bearing:

* The database URL comes from ``backend.database.database_url()`` — the same
  resolution the application uses — so ``make migrate`` and a running server
  can never end up pointed at different databases.
* ``render_as_batch=True`` is required, not cosmetic. SQLite cannot
  ``ALTER TABLE`` for most column and constraint changes, and this project has
  no database but SQLite; batch mode is what makes future column additions
  runnable.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, Engine

from backend.database import Base, create_database_engine, database_url
from backend.migrator import MIGRATION_CONTEXT_OPTIONS

# Importing the module registers every table on Base.metadata, which is what
# `alembic revision --autogenerate` compares the database against.
from backend import db_models  # noqa: F401


config = context.config

# A caller that hands us a live connection (DatabaseStore) owns its own
# logging; only reconfigure logging when alembic runs as a command line tool.
_connection: Connection | None = config.attributes.get("connection")
if config.config_file_name is not None and _connection is None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _context_options() -> dict[str, object]:
    return {"target_metadata": target_metadata, **MIGRATION_CONTEXT_OPTIONS}


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it against a database."""
    context.configure(
        url=database_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_context_options(),
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, **_context_options())
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection.

    ``config.attributes["connection"]`` is set when the application upgrades its
    own database in process. Reusing that exact connection is mandatory: the test
    suite's ``sqlite+pysqlite:///:memory:`` database lives in a single connection
    held open by ``StaticPool``, and a second connection to it would see — and
    migrate — an empty database.
    """
    connection = config.attributes.get("connection")
    if connection is not None:
        _run_migrations(connection)
        return

    connectable = config.attributes.get("engine")
    if not isinstance(connectable, Engine):
        connectable = create_database_engine(database_url())
    with connectable.connect() as new_connection:
        _run_migrations(new_connection)
        new_connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
