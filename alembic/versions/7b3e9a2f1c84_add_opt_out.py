"""add_opt_out

Revision ID: 7b3e9a2f1c84
Revises: 09f197516925
Create Date: 2026-02-21 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7b3e9a2f1c84'
down_revision: Union[str, None] = '09f197516925'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'opt_out',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('platform', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('platform_author_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_opt_out_platform'), 'opt_out', ['platform'], unique=False)
    op.create_index(op.f('ix_opt_out_platform_author_id'), 'opt_out', ['platform_author_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_opt_out_platform_author_id'), table_name='opt_out')
    op.drop_index(op.f('ix_opt_out_platform'), table_name='opt_out')
    op.drop_table('opt_out')
