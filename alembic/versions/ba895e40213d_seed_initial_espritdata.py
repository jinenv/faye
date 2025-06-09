"""Seed initial EspritData

Revision ID: ba895e40213d
Revises: 1c81f10e2ea1
Create Date: 2025-06-09 07:09:19.168305

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ba895e40213d'
down_revision: Union[str, None] = '1c81f10e2ea1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
