"""Seed initial EspritData

Revision ID: c8a6d054f6c5
Revises: ba895e40213d
Create Date: 2025-06-09 07:12:12.356422

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8a6d054f6c5'
down_revision: Union[str, None] = 'ba895e40213d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
