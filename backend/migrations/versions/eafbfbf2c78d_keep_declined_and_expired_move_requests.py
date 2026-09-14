"""keep declined and expired move requests

A move request used to be deleted the moment it was resolved, so the table held
nothing but pending rows and "a row exists" meant "someone is waiting for an
answer". Declining now keeps the row (#10): ``status`` becomes ``declined``
with an optional ``decline_reason``, and a request that goes stale on its own
becomes ``expired``. ``resolved_at`` stamps when it left ``pending``.

The dangerous half of that is not the columns, it is the two unique indexes.
``ix_lesson_move_requests_lesson_id`` and
``ix_lesson_move_requests_requested_starts_at`` were unconditional, which said
"one row per lesson and one row per requested time, ever". That was true while
resolving deleted the row and becomes a permanent block the moment it does not:
a lesson's first decline would own that ``lesson_id`` forever and the student
could never request a move for that lesson again. Both are recreated below
scoped to ``WHERE status = 'pending'``, which makes a resolved row inert
history rather than a lasting claim.

Why this is not one ``op.batch_alter_table`` block, as the issue first asked:

* Adding the three **columns** under batch is fine and is what happens below.
  With a plain-string ``server_default`` alembic stays on SQLite's native
  ``ALTER TABLE ... ADD COLUMN`` and never rebuilds the table
  (``alembic/ddl/sqlite.py:46``, ``requires_recreate_in_batch``). Note that
  spelling the default as ``sa.text("'pending'")`` would flip that to a rebuild.
* Adding the ``CHECK`` constraint cannot be. SQLite has no ``ALTER TABLE ADD
  CONSTRAINT``, so batch would rebuild, and a batch rebuild ends in ``ALTER
  TABLE _alembic_tmp_... RENAME TO ...``. SQLite rewrites a renamed table's
  stored DDL with a *quoted* name, which is not what ``create_all`` emits, and
  batch collects the constraints to carry over by iterating a ``set``, so the
  emitted order changes between runs. Both break ``tests/test_migrations.py``,
  the second one flakily. Measured during #13, tracked as #56.

So the rebuild is written out, in the same copy-table shape as
``ac812725de6c`` and for the same reasons: through a copy table rather than a
rename, with the constraints listed in the order ``db_models.py`` declares
them, and with the row check done *before* anything is created or dropped.
That last point is the one that matters most: under pysqlite SQLite runs DDL
outside the surrounding transaction, so a failure partway through a rebuild
raises with the real table already dropped and recreated empty and the rows
surviving only in the copy. Refusing up front means the table is never touched
when a row cannot make it across.

Types are spelled out (``sa.DateTime(timezone=True)``, ``sa.String(20)``)
rather than imported from ``backend.db_models``, like every revision before it:
a migration must not change under you when the application code does.

Revision ID: eafbfbf2c78d
Revises: ac812725de6c
Create Date: 2026-09-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eafbfbf2c78d'
down_revision: Union[str, Sequence[str], None] = 'ac812725de6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "lesson_move_requests"
COPY_TABLE = "lesson_move_requests_status_rebuild"

RESOLVED_COLUMNS = "id, lesson_id, requested_starts_at, status, decline_reason, resolved_at"
PENDING_ONLY_COLUMNS = "id, lesson_id, requested_starts_at"

STATUS_IS_KNOWN = "status IN ('pending', 'declined', 'expired')"
PENDING_ONLY = "status = 'pending'"


def _lesson_id_index() -> str:
    return op.f("ix_lesson_move_requests_lesson_id")


def _requested_starts_at_index() -> str:
    return op.f("ix_lesson_move_requests_requested_starts_at")


def upgrade() -> None:
    """Upgrade schema."""
    # 1. The columns. Native ADD COLUMN, no rebuild, every existing row lands on
    #    'pending' -- exactly the state its mere existence used to imply.
    with op.batch_alter_table(TABLE, schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("status", sa.String(20), nullable=False, server_default="pending")
        )
        batch_op.add_column(sa.Column("decline_reason", sa.String(500), nullable=True))
        batch_op.add_column(
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True)
        )

    # 2. The CHECK constraint, written out. Nothing can fail this check -- step 1
    #    has just set every row to 'pending' -- but the count runs first anyway,
    #    because a rebuild that raises after the DROP loses the table's rows.
    bind = op.get_bind()
    unknown = bind.execute(
        sa.text(f"SELECT count(*) FROM {TABLE} WHERE NOT ({STATUS_IS_KNOWN})")  # noqa: S608
    ).scalar()
    if unknown:
        raise RuntimeError(
            f"{unknown} move request(s) hold a status outside {STATUS_IS_KNOWN} and this "
            "migration will not invent one for them. Decide what those requests are, "
            "change them, and run it again."
        )
    op.execute(f"CREATE TABLE {COPY_TABLE} AS SELECT {RESOLVED_COLUMNS} FROM {TABLE}")
    # Dropping the table takes the two unconditional unique indexes with it,
    # which is the drop the issue calls for; the partial ones are created below.
    op.drop_table(TABLE)
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("requested_starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("decline_reason", sa.String(length=500), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lesson_move_requests")),
        sa.CheckConstraint(
            STATUS_IS_KNOWN, name=op.f("ck_lesson_move_requests_move_request_status")
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["lessons.id"],
            name=op.f("fk_lesson_move_requests_lesson_id_lessons"),
        ),
    )
    op.execute(f"INSERT INTO {TABLE} ({RESOLVED_COLUMNS}) SELECT {RESOLVED_COLUMNS} FROM {COPY_TABLE}")
    op.drop_table(COPY_TABLE)

    # 3. The partial unique indexes. Plain DDL: SQLite creates and drops an index
    #    without touching the table, so these stay outside any batch block.
    op.create_index(
        _lesson_id_index(),
        TABLE,
        ["lesson_id"],
        unique=True,
        sqlite_where=sa.text(PENDING_ONLY),
    )
    op.create_index(
        _requested_starts_at_index(),
        TABLE,
        ["requested_starts_at"],
        unique=True,
        sqlite_where=sa.text(PENDING_ONLY),
    )


def downgrade() -> None:
    """Downgrade schema.

    Lossy in one direction only, and it refuses rather than guessing. The old
    schema has no way to say "declined" or "expired": every row it holds is a
    pending request, and its unique indexes are unconditional. Carrying a
    resolved row back would either resurrect it as a live request blocking its
    lesson and its slot, or collide with a newer pending row on the very index
    being restored.

    So a resolved row stops the downgrade, with nothing dropped and nothing
    changed. Whoever needs to go back decides first what should happen to that
    history -- in a data fix of their own -- and runs this again. A database
    holding only pending requests, which is every database that never used the
    feature, goes back losslessly.

    ``DatabaseStore.reset`` empties every table before unwinding the schema, so
    the test suite's downgrade never meets a resolved row and this guard does
    not get in its way.
    """
    bind = op.get_bind()
    resolved = bind.execute(
        sa.text(f"SELECT count(*) FROM {TABLE} WHERE NOT ({PENDING_ONLY})")  # noqa: S608
    ).scalar()
    if resolved:
        raise RuntimeError(
            f"{resolved} move request(s) have been declined or have expired, and the "
            "schema being restored can only hold pending ones. Decide what that history "
            "should become, remove those rows, and run it again."
        )
    op.execute(f"CREATE TABLE {COPY_TABLE} AS SELECT {PENDING_ONLY_COLUMNS} FROM {TABLE}")
    op.drop_table(TABLE)
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("requested_starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lesson_move_requests")),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["lessons.id"],
            name=op.f("fk_lesson_move_requests_lesson_id_lessons"),
        ),
    )
    op.execute(
        f"INSERT INTO {TABLE} ({PENDING_ONLY_COLUMNS}) "  # noqa: S608
        f"SELECT {PENDING_ONLY_COLUMNS} FROM {COPY_TABLE}"
    )
    op.drop_table(COPY_TABLE)
    op.create_index(_lesson_id_index(), TABLE, ["lesson_id"], unique=True)
    op.create_index(_requested_starts_at_index(), TABLE, ["requested_starts_at"], unique=True)
