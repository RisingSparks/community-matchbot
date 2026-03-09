"""add_community_perf_indexes

Revision ID: f2b1c3d4e5f6
Revises: ce8d9b8f4c12
Create Date: 2026-03-09 10:50:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2b1c3d4e5f6"
down_revision: str | None = "ce8d9b8f4c12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_post_detected_at"),
        "post",
        ["detected_at"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_post_extraction_method"),
        "post",
        ["extraction_method"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_match_created_at"),
        "match",
        ["created_at"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_match_intro_sent_at"),
        "match",
        ["intro_sent_at"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_match_intro_sent_at"), table_name="match")
    op.drop_index(op.f("ix_match_created_at"), table_name="match")
    op.drop_index(op.f("ix_post_extraction_method"), table_name="post")
    op.drop_index(op.f("ix_post_detected_at"), table_name="post")
