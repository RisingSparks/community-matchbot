"""Add unique constraint to match seeker/camp pairs.

Revision ID: d4f6e8a1b2c3
Revises: f2b1c3d4e5f6
Create Date: 2026-04-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4f6e8a1b2c3"
down_revision: Union[str, Sequence[str], None] = "f2b1c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("match", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_match_seeker_camp",
            ["seeker_post_id", "camp_post_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("match", schema=None) as batch_op:
        batch_op.drop_constraint("uq_match_seeker_camp", type_="unique")
