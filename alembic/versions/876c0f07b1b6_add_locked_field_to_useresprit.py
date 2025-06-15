"""Add locked field to UserEsprit

Revision ID: 876c0f07b1b6
Revises: 6c07a3b7d02c
Create Date: 2025-06-14 21:55:47.594803

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '876c0f07b1b6'
down_revision: Union[str, None] = '6c07a3b7d02c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user_esprits',
        sa.Column('locked', sa.Boolean(), nullable=False, server_default=sa.false())
    )

def downgrade() -> None:
    op.drop_column('user_esprits', 'locked')

