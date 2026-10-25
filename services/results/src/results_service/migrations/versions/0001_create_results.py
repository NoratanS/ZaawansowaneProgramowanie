"""Create the results table.

Revision ID: 0001
Revises:
Create Date: 2026-10-25
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Mirrors the succeeded/failed shape rules of the Analysis Result.
RESULT_SHAPE = """
(
    status = 'succeeded'
    AND person_count IS NOT NULL
    AND detections IS NOT NULL
    AND error_code IS NULL
    AND error_message IS NULL
) OR (
    status = 'failed'
    AND person_count IS NULL
    AND detections IS NULL
    AND error_code IS NOT NULL
    AND error_message IS NOT NULL
)
"""


def upgrade():
    op.create_table(
        "results",
        sa.Column("job_id", sa.Uuid(), primary_key=True),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("person_count", sa.Integer(), nullable=True),
        sa.Column("detections", postgresql.JSONB(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "stored_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(RESULT_SHAPE, name="ck_results_shape"),
        sa.CheckConstraint(
            "person_count >= 0", name="ck_results_person_count_non_negative"
        ),
    )
    op.create_index("ix_results_stored_at", "results", ["stored_at"])


def downgrade():
    op.drop_index("ix_results_stored_at", table_name="results")
    op.drop_table("results")
