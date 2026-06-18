"""add_unmapped_taxonomy_fields_to_post

Revision ID: ce8d9b8f4c12
Revises: c3f7a1b2d901
Create Date: 2026-03-09 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ce8d9b8f4c12"
down_revision: str | None = "c3f7a1b2d901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "post",
        sa.Column(
            "vibes_other", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""
        ),
    )
    op.add_column(
        "post",
        sa.Column(
            "contribution_types_other",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "post",
        sa.Column(
            "infra_categories_other",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "post",
        sa.Column("condition_other", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("post", "condition_other")
    op.drop_column("post", "infra_categories_other")
    op.drop_column("post", "contribution_types_other")
    op.drop_column("post", "vibes_other")
