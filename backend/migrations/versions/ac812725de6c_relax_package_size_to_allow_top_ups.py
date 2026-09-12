"""relax package size to allow top ups

Renewing a package tops it up in place (#13): the existing row's ``size`` goes
up by the amount bought, so a 10 renewed by 10 becomes a 20 and 5 + 8 + 5
becomes an 18. ``CHECK (size IN (5, 8, 10))`` cannot express that, so it becomes
``CHECK (size >= 1)``. The sizes that can be *bought* in one go are still 5, 8
and 10; that rule lives in ``PackageRequest``, not in the database.

SQLite has no ``ALTER TABLE ... DROP CONSTRAINT``, so changing a ``CHECK`` means
rebuilding the table: copy the rows aside, drop it, create it with the new
constraint, copy the rows back. That is exactly what ``op.batch_alter_table``
does for you, and the issue asked for it -- but it cannot be used here, for two
reasons that were measured rather than guessed (see the note on #13):

* Batch finishes with ``ALTER TABLE _alembic_tmp_packages RENAME TO packages``,
  and SQLite rewrites the stored DDL of a renamed table with a *quoted* name.
  ``CREATE TABLE "packages"`` is not the ``CREATE TABLE packages`` that
  ``Base.metadata.create_all`` emits, and
  ``test_initial_revision_reproduces_the_create_all_schema`` compares that text.
* Batch collects the constraints to carry over by iterating ``Table.constraints``,
  which is a ``set``. The order they land in the rebuilt DDL changes from run to
  run, so the same migration produces a different ``CREATE TABLE`` each time and
  ``test_migrations_round_trip_leaves_the_same_schema`` becomes a coin flip.

The rebuild below is the same four steps, written out, with the constraints
listed in the order ``db_models.py`` declares them. It goes through a copy table
rather than renaming ``packages``, because a modern SQLite rewrites the foreign
key in ``lessons`` to follow a renamed table.

``copy_from``-style type spellings: ``sa.Boolean()`` and friends are written out
here, not imported from ``backend.db_models``, for the same reason the earlier
revisions spell ``sa.DateTime(timezone=True)`` out -- a migration must not change
under you when the application code does.

Revision ID: ac812725de6c
Revises: 634fd3641913
Create Date: 2026-09-12 19:37:57.671869

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ac812725de6c'
down_revision: Union[str, Sequence[str], None] = '634fd3641913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SIZE_IS_A_PRICE_LIST_SIZE = "size IN (5, 8, 10)"
SIZE_IS_A_RUNNING_TOTAL = "size >= 1"

COPY_TABLE = "packages_size_rebuild"
COLUMNS = "id, student_id, size, used, period_no, invoice_sent"


def _rebuild_packages_with(size_check: str) -> None:
    """Rebuild ``packages`` carrying ``size_check`` on ``size``, rows and all.

    Every row goes through the new table's constraints on the way back in, which
    is what makes the downgrade below refuse rather than quietly lose data.
    """
    op.execute(f"CREATE TABLE {COPY_TABLE} AS SELECT {COLUMNS} FROM packages")
    op.drop_table("packages")
    op.create_table(
        "packages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("used", sa.Integer(), nullable=False),
        sa.Column("period_no", sa.Integer(), nullable=False),
        sa.Column("invoice_sent", sa.Boolean(), nullable=False),
        sa.CheckConstraint(size_check, name=op.f("ck_packages_valid_size")),
        sa.CheckConstraint("used >= 0 AND used <= size", name=op.f("ck_packages_used_range")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_packages")),
        sa.UniqueConstraint("student_id", "period_no", name=op.f("uq_packages_student_id")),
        sa.ForeignKeyConstraint(
            ["student_id"], ["students.id"], name=op.f("fk_packages_student_id_students")
        ),
    )
    op.execute(f"INSERT INTO packages ({COLUMNS}) SELECT {COLUMNS} FROM {COPY_TABLE}")
    op.drop_table(COPY_TABLE)
    # Last: the old table's index kept its name through the rebuild and is only
    # gone once that table is.
    with op.batch_alter_table("packages", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_packages_student_id"), ["student_id"], unique=False)


def upgrade() -> None:
    """Upgrade schema."""
    _rebuild_packages_with(SIZE_IS_A_RUNNING_TOTAL)


def downgrade() -> None:
    """Downgrade schema.

    Lossy by design, and loudly so. Going back narrows ``size`` to 5, 8 or 10
    again, and a package that has been topped up -- to 20, or to 16 -- has no
    value under the old rule that it could be changed to without one being
    invented for it.

    So this does not clamp and it does not delete. The rows are copied back into
    a table carrying the old ``CHECK``, SQLite refuses the topped-up ones, and
    the migration raises: the transaction rolls back with every package still
    exactly as it was. Whoever needs to go back has to decide first what a
    topped-up package should become, and say so in a data fix of their own.
    """
    _rebuild_packages_with(SIZE_IS_A_PRICE_LIST_SIZE)
