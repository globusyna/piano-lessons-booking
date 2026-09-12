"""add student_pauses

The table behind pausing a student for 1-6 weeks (#12): one row per break, with
the dates it covers rather than just a duration, so a pause can be queried and
displayed without re-deriving it.

``created_at`` / ``ended_early_at`` are ``backend.database.UtcDateTime`` on the
model, a ``TypeDecorator`` over ``DateTime(timezone=True)``. The decorator only
converts values in Python, so it emits exactly the same DDL; autogenerate
rendered it as ``backend.database.UtcDateTime(timezone=True)``, which this file
does not import. It is spelled ``sa.DateTime(timezone=True)`` here for the same
reason the initial revision does: a migration must not depend on application
code that may change under it.

Revision ID: 634fd3641913
Revises: 256042e4926e
Create Date: 2026-09-12 19:07:25.462283

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '634fd3641913'
down_revision: Union[str, Sequence[str], None] = '256042e4926e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('student_pauses',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.Column('weeks', sa.Integer(), nullable=False),
    sa.Column('starts_on', sa.Date(), nullable=False),
    sa.Column('ends_on', sa.Date(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ended_early_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('weeks >= 1 AND weeks <= 6', name=op.f('ck_student_pauses_pause_weeks_range')),
    sa.ForeignKeyConstraint(['student_id'], ['students.id'], name=op.f('fk_student_pauses_student_id_students')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_student_pauses'))
    )
    with op.batch_alter_table('student_pauses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_student_pauses_ends_on'), ['ends_on'], unique=False)
        batch_op.create_index(batch_op.f('ix_student_pauses_student_id'), ['student_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('student_pauses', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_student_pauses_student_id'))
        batch_op.drop_index(batch_op.f('ix_student_pauses_ends_on'))

    op.drop_table('student_pauses')
