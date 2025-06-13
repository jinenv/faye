"""Add pity counters and update power logic

Revision ID: 4c76c73bb371
Revises: 4da95b51e9ba
Create Date: 2025-06-12 19:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4c76c73bb371'
down_revision: Union[str, None] = '4da95b51e9ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### Manually corrected Alembic commands ###
    # We add server_default='0' to tell SQLite what value to use for existing rows.
    op.add_column('user', sa.Column('pity_count_standard', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('user', sa.Column('pity_count_premium', sa.Integer(), nullable=False, server_default='0'))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### Manually corrected Alembic commands ###
    op.drop_column('user', 'pity_count_standard')
    op.drop_column('user', 'pity_count_premium')
    # ### end Alembic commands ###

