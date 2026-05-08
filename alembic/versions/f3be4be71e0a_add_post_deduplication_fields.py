"""add_post_deduplication_fields

Revision ID: f3be4be71e0a
Revises: cde0fbf70a21
Create Date: 2026-05-08 13:06:21.016749

"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f3be4be71e0a'
down_revision: str | None = 'cde0fbf70a21'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("post") as batch_op:
        batch_op.add_column(
            sa.Column("content_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("minhash_sigs", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("parent_post_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )
        batch_op.create_index(op.f("ix_post_content_hash"), ["content_hash"], unique=False)
        batch_op.create_index(op.f("ix_post_parent_post_id"), ["parent_post_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_post_parent_post_id_post",
            "post",
            ["parent_post_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("post") as batch_op:
        batch_op.drop_constraint("fk_post_parent_post_id_post", type_="foreignkey")
        batch_op.drop_index(op.f("ix_post_parent_post_id"))
        batch_op.drop_index(op.f("ix_post_content_hash"))
        batch_op.drop_column("parent_post_id")
        batch_op.drop_column("minhash_sigs")
        batch_op.drop_column("content_hash")
