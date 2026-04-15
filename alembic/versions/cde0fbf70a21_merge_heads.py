"""merge_heads

Revision ID: cde0fbf70a21
Revises: c1a2b3d4e5f7, d4f6e8a1b2c3
Create Date: 2026-04-15 07:29:03.047285

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'cde0fbf70a21'
down_revision: Union[str, None] = ('c1a2b3d4e5f7', 'd4f6e8a1b2c3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
