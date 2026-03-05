"""add_source_created_at_to_post

Revision ID: 8d1b8e1e2f77
Revises: 47a9e3528006
Create Date: 2026-03-04 23:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8d1b8e1e2f77'
down_revision: Union[str, None] = '47a9e3528006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('post', sa.Column('source_created_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('post', 'source_created_at')
