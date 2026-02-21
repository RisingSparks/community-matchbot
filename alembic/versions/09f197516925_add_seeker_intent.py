"""add_seeker_intent

Revision ID: 09f197516925
Revises: 4a8a055657bf
Create Date: 2026-02-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '09f197516925'
down_revision: Union[str, None] = '4a8a055657bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('post', sa.Column('seeker_intent', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('profile', sa.Column('seeker_intent', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    op.drop_column('profile', 'seeker_intent')
    op.drop_column('post', 'seeker_intent')
