"""Add index to EspritData.rarity

Revision ID: 2aa0a1a86f31
Revises: a0a18afacf82
Create Date: 2025-06-13 08:09:19.616249

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '2aa0a1a86f31'
down_revision = 'a0a18afacf82'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Drop if it somehow exists, then (re-)create
    op.drop_index(
        "ix_espritdata_rarity",
        table_name="espritdata",
        if_exists=True,          # <- works on SQLAlchemy 2.0
    )
    op.create_index(
        "ix_espritdata_rarity",
        "espritdata",
        ["rarity"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_espritdata_rarity", table_name="espritdata")


