"""add_display_title_to_post

Revision ID: c1a2b3d4e5f7
Revises: a9fa3d135aaf
Create Date: 2026-04-15 11:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "c1a2b3d4e5f7"
down_revision: Union[str, None] = "a9fa3d135aaf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("post", sa.Column("display_title", sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    op.drop_column("post", "display_title")
