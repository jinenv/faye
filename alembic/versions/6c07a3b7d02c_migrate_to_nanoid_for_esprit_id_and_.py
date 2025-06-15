"""migrate to NanoID for esprit_id and user_esprit.id

Revision ID: 6c07a3b7d02c
Revises: fea3f4f37bd4
Create Date: 2025-06-14 19:55:33.722382

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6c07a3b7d02c'
down_revision: Union[str, None] = 'fea3f4f37bd4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DELETE FROM user_esprits")
    op.execute("DELETE FROM esprit_data")

def downgrade() -> None:
    pass
