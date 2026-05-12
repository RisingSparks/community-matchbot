"""add_infra_offer_details_to_post

Revision ID: a1b2c3d4e5f8
Revises: 53561b998723
Create Date: 2026-05-12 14:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f8"
down_revision: str | None = "53561b998723"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("post") as batch_op:
        batch_op.add_column(
            sa.Column("infra_offer_type", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("pickup_location", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )
        batch_op.add_column(sa.Column("delivery_available", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("dimensions", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(
            sa.Column("parts_included", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )
        batch_op.add_column(sa.Column("setup_notes", sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("post") as batch_op:
        batch_op.drop_column("setup_notes")
        batch_op.drop_column("parts_included")
        batch_op.drop_column("dimensions")
        batch_op.drop_column("delivery_available")
        batch_op.drop_column("pickup_location")
        batch_op.drop_column("infra_offer_type")
