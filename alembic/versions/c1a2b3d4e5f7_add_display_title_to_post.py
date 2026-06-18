"""add_display_title_to_post

Revision ID: c1a2b3d4e5f7
Revises: a9fa3d135aaf
Create Date: 2026-04-15 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1a2b3d4e5f7"
down_revision: str | None = "a9fa3d135aaf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "post", sa.Column("display_title", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("post", "display_title")
