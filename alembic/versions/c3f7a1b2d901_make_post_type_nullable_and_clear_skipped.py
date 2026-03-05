"""make_post_type_nullable_and_clear_skipped

Revision ID: c3f7a1b2d901
Revises: 8d1b8e1e2f77
Create Date: 2026-03-05 09:20:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3f7a1b2d901'
down_revision: str | None = '8d1b8e1e2f77'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column('post', 'post_type', existing_type=sa.String(), nullable=True)
    op.execute("UPDATE post SET post_type = NULL WHERE status = 'skipped'")


def downgrade() -> None:
    op.execute("UPDATE post SET post_type = 'mentorship' WHERE post_type IS NULL")
    op.alter_column('post', 'post_type', existing_type=sa.String(), nullable=False)
