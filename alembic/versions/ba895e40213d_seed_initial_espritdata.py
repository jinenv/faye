"""Seed initial EspritData

Revision ID: ba895e40213d
Revises: 1c81f10e2ea1
Create Date: 2025-06-09 07:09:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import json
import os

# revision identifiers, used by Alembic.
# IMPORTANT: Manually update these two IDs to match your generated files.
revision: str = 'ba895e40213d'
down_revision: Union[str, None] = '1c81f10e2ea1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Define the table structure for the bulk insert operation.
    # This ensures the script doesn't depend on the full model definition.
    esprit_table = sa.table('espritdata',
        sa.column('esprit_id', sa.String),
        sa.column('name', sa.String),
        sa.column('description', sa.String),
        sa.column('rarity', sa.String),
        sa.column('class_name', sa.String),
        sa.column('visual_asset_path', sa.String),
        sa.column('base_hp', sa.Integer),
        sa.column('base_attack', sa.Integer),
        sa.column('base_defense', sa.Integer),
        sa.column('base_speed', sa.Integer),
        sa.column('base_magic_resist', sa.Integer),
        sa.column('base_crit_rate', sa.Float),
        sa.column('base_block_rate', sa.Float),
        sa.column('base_dodge_chance', sa.Float),
        sa.column('base_mana_regen', sa.Integer),
        sa.column('base_mana', sa.Integer)
    )

    # Construct the path to the JSON file relative to the project root.
    json_path = os.path.join('data', 'config', 'esprits.json')

    with open(json_path, 'r', encoding='utf-8') as f:
        esprits_data = json.load(f)

    esprits_to_insert = []
    for esprit_id, data in esprits_data.items():
        esprits_to_insert.append({
            'esprit_id': esprit_id,
            'name': data.get('name', 'Unknown'),
            'description': data.get('description', ''),
            'rarity': data.get('rarity', 'Common'),
            'class_name': data.get('class_name', 'Unknown'),
            'visual_asset_path': data.get('visual_asset_path', ''),
            'base_hp': data.get('base_hp', 0),
            'base_attack': data.get('base_attack', 0),
            'base_defense': data.get('base_defense', 0),
            'base_speed': data.get('base_speed', 0),
            'base_magic_resist': data.get('base_magic_resist', 0),
            'base_crit_rate': data.get('base_crit_rate', 0.0),
            'base_block_rate': data.get('base_block_rate', 0.0),
            'base_dodge_chance': data.get('base_dodge_chance', 0.0),
            'base_mana_regen': data.get('base_mana_regen', 0),
            'base_mana': data.get('base_mana', 0)
        })
    
    # Perform the bulk insert.
    if esprits_to_insert:
        op.bulk_insert(esprit_table, esprits_to_insert)


def downgrade() -> None:
    # On downgrade, remove all data from the table, making it reversible.
    op.execute("DELETE FROM espritdata")