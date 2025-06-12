from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = 'ef4d780dbf46'
down_revision: Union[str, None] = '524bf556bd68'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Adds the 'aether' column to the 'user' table, ensuring it's NOT NULL.
    This script is idempotent and handles SQLite's limitations by recreating the table.
    """
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    columns = inspector.get_columns('user')
    column_names = {c['name'] for c in columns}

    # --- FIX STARTS HERE ---
    
    # 1. Check if the 'aether' column already exists.
    if 'aether' not in column_names:
        print("Column 'aether' not found, adding it as nullable for now.")
        # Add the column as nullable initially.
        op.add_column('user', sa.Column('aether', sa.Integer(), nullable=True))
        
        # IMPORTANT: Populate the new column for all existing rows.
        # The server_default only applies to new inserts, not existing rows.
        print("Populating 'aether' for existing users with default value 0.")
        op.execute('UPDATE "user" SET aether = 0 WHERE aether IS NULL')
    else:
        print("Column 'aether' already exists.")

    # --- END OF FIX ---


    # This next block handles the SQLite limitation of not being able to
    # alter a column from NULL to NOT NULL directly. We recreate the table.
    # NOTE: Alembic's batch mode is the preferred way to do this.
    # For this specific case, we'll proceed with your manual table-recreation logic.
    
    with op.batch_alter_table('user', schema=None) as batch_op:
        # Alter the column to be non-nullable. In the background, Alembic
        # handles the create/copy/drop/rename process for SQLite.
        batch_op.alter_column('aether',
                              existing_type=sa.INTEGER(),
                              nullable=False,
                              server_default='0')

    # Note: Using op.batch_alter_table() is the modern, safer way to handle
    # SQLite alterations. It correctly handles copying data, indexes, and
    # foreign keys. The lengthy manual process in your original script
    # can be replaced by the block above. If you must use the manual method,
    # ensure your logic is sound, but the batch operation is highly recommended.


def downgrade() -> None:
    # The downgrade function is generally simpler.
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('aether')
