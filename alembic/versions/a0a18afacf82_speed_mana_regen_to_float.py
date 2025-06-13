"""speed+mana_regen to float

Revision ID: a0a18afacf82
Revises: 4c76c73bb371
Create Date: 2025-06-12 21:46:02.708500

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a0a18afacf82'
down_revision: Union[str, None] = '4c76c73bb371'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("espritdata") as batch:
        batch.alter_column("base_speed",
                           existing_type=sa.INTEGER(),
                           type_=sa.FLOAT())
        batch.alter_column("base_mana_regen",
                           existing_type=sa.INTEGER(),
                           type_=sa.FLOAT())

def downgrade() -> None:
    with op.batch_alter_table("espritdata") as batch:
        batch.alter_column("base_speed",
                           existing_type=sa.FLOAT(),
                           type_=sa.INTEGER())
        batch.alter_column("base_mana_regen",
                           existing_type=sa.FLOAT(),
                           type_=sa.INTEGER())

