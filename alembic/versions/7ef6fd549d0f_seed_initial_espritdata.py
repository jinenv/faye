"""Seed initial EspritData

Revision ID: 7ef6fd549d0f
Revises: 0999c9acdca5
Create Date: 2025-06-08 21:24:12.228654

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7ef6fd549d0f'
down_revision: Union[str, None] = '0999c9acdca5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
