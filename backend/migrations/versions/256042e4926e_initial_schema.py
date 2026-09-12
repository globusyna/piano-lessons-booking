"""initial schema

The schema ``Base.metadata.create_all`` produced before migrations existed: the
six tables in ``backend/db_models.py`` with their constraints and indexes.

``starts_at`` / ``requested_starts_at`` are ``backend.database.UtcDateTime`` on
the models, a ``TypeDecorator`` over ``DateTime(timezone=True)``. The decorator
only converts values in Python, so it emits exactly the same DDL; spelling it
``sa.DateTime(timezone=True)`` here keeps the migration independent of
application code.

Revision ID: 256042e4926e
Revises: 
Create Date: 2026-09-12 16:26:01.307809

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '256042e4926e'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('availability_slots',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('weekday', sa.Integer(), nullable=False),
    sa.Column('local_time', sa.String(length=5), nullable=False),
    sa.CheckConstraint('weekday >= 1 AND weekday <= 5', name=op.f('ck_availability_slots_weekday_range')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_availability_slots')),
    sa.UniqueConstraint('weekday', 'local_time', name=op.f('uq_availability_slots_weekday'))
    )
    with op.batch_alter_table('availability_slots', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_availability_slots_weekday'), ['weekday'], unique=False)

    op.create_table('blackouts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('note', sa.String(length=500), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_blackouts'))
    )
    with op.batch_alter_table('blackouts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_blackouts_starts_at'), ['starts_at'], unique=True)

    op.create_table('students',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('token', sa.String(length=255), nullable=False),
    sa.Column('slot_day', sa.Integer(), nullable=False),
    sa.Column('slot_time', sa.String(length=5), nullable=False),
    sa.CheckConstraint('slot_day >= 1 AND slot_day <= 5', name=op.f('ck_students_slot_day_range')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_students'))
    )
    with op.batch_alter_table('students', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_students_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_students_token'), ['token'], unique=True)

    op.create_table('teacher_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=100), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('timezone', sa.String(length=100), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_teacher_settings')),
    sa.UniqueConstraint('username', name=op.f('uq_teacher_settings_username'))
    )
    op.create_table('packages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.Column('used', sa.Integer(), nullable=False),
    sa.Column('period_no', sa.Integer(), nullable=False),
    sa.Column('invoice_sent', sa.Boolean(), nullable=False),
    sa.CheckConstraint('size IN (5, 8, 10)', name=op.f('ck_packages_valid_size')),
    sa.CheckConstraint('used >= 0 AND used <= size', name=op.f('ck_packages_used_range')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_packages')),
    sa.UniqueConstraint('student_id', 'period_no', name=op.f('uq_packages_student_id')),
    sa.ForeignKeyConstraint(['student_id'], ['students.id'], name=op.f('fk_packages_student_id_students'))
    )
    with op.batch_alter_table('packages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_packages_student_id'), ['student_id'], unique=False)

    op.create_table('lessons',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.Column('package_id', sa.Integer(), nullable=False),
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.CheckConstraint('seq >= 1', name=op.f('ck_lessons_positive_sequence')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_lessons')),
    sa.UniqueConstraint('starts_at', name=op.f('uq_lessons_starts_at')),
    sa.ForeignKeyConstraint(['student_id'], ['students.id'], name=op.f('fk_lessons_student_id_students')),
    sa.ForeignKeyConstraint(['package_id'], ['packages.id'], name=op.f('fk_lessons_package_id_packages'))
    )
    with op.batch_alter_table('lessons', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_lessons_package_id'), ['package_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_lessons_starts_at'), ['starts_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_lessons_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_lessons_student_id'), ['student_id'], unique=False)

    op.create_table('lesson_move_requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('lesson_id', sa.Integer(), nullable=False),
    sa.Column('requested_starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['lesson_id'], ['lessons.id'], name=op.f('fk_lesson_move_requests_lesson_id_lessons')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_lesson_move_requests'))
    )
    with op.batch_alter_table('lesson_move_requests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_lesson_move_requests_lesson_id'), ['lesson_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_lesson_move_requests_requested_starts_at'), ['requested_starts_at'], unique=True)



def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('lesson_move_requests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_lesson_move_requests_requested_starts_at'))
        batch_op.drop_index(batch_op.f('ix_lesson_move_requests_lesson_id'))

    op.drop_table('lesson_move_requests')
    with op.batch_alter_table('lessons', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_lessons_student_id'))
        batch_op.drop_index(batch_op.f('ix_lessons_status'))
        batch_op.drop_index(batch_op.f('ix_lessons_starts_at'))
        batch_op.drop_index(batch_op.f('ix_lessons_package_id'))

    op.drop_table('lessons')
    with op.batch_alter_table('packages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_packages_student_id'))

    op.drop_table('packages')
    op.drop_table('teacher_settings')
    with op.batch_alter_table('students', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_students_token'))
        batch_op.drop_index(batch_op.f('ix_students_status'))

    op.drop_table('students')
    with op.batch_alter_table('blackouts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_blackouts_starts_at'))

    op.drop_table('blackouts')
    with op.batch_alter_table('availability_slots', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_availability_slots_weekday'))

    op.drop_table('availability_slots')
