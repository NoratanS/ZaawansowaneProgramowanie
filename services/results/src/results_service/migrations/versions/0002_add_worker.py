"""Add the worker that produced each Result.

Nullable: rows stored before this revision have no worker.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-15
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("results", sa.Column("worker", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("results", "worker")
