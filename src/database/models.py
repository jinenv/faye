# src/database/models.py
from typing import Optional, List
from datetime import datetime
import sqlalchemy as sa
from sqlmodel import Field, SQLModel, Relationship

class EspritData(SQLModel, table=True):
    """Stores the static, base data for every type of Esprit."""
    esprit_id: str = Field(primary_key=True, index=True)
    name: str
    description: str
    rarity: str
    class_name: str = Field(default="Unknown")
    visual_asset_path: str
    base_hp: int
    base_attack: int
    base_defense: int
    base_speed: int
    base_magic_resist: int = 0
    base_crit_rate: float = 0.0
    base_block_rate: float = 0.0
    base_dodge_chance: float = 0.0
    base_mana_regen: int = 0
    base_mana: int = 0
    owners: List["UserEsprit"] = Relationship(back_populates="esprit_data")

class User(SQLModel, table=True):
    """Stores data for each registered player."""
    user_id: str = Field(primary_key=True, index=True)
    username: str
    level: int = Field(default=1)
    xp: int = Field(default=0)
    
    # --- CURRENCY RESTRUCTURE (per directive) ---
    nyxies: int = Field(default=0, nullable=False)        # Replaces 'gold'
    moonglow: int = Field(default=0, nullable=False)      # Replaces 'dust'
    azurite_shards: int = Field(default=0, nullable=False) # Replaces 'fragments'
    essence: int = Field(default=0, nullable=False)       # New crafting material
    
    # --- OTHER INVENTORY & METADATA ---
    loot_chests: int = Field(default=0, nullable=False)
    last_daily_claim: Optional[datetime] = Field(default=None, nullable=True)
    created_at: datetime = Field(
        default=None,
        sa_column=sa.Column(
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp()
        )
    )
    
    # --- TEAM MANAGEMENT (per directive) ---
    # Foreign Keys to the UserEsprit table's 'id' field.
    active_esprit_id: Optional[str] = Field(default=None, foreign_key="useresprit.id", nullable=True)
    support1_esprit_id: Optional[str] = Field(default=None, foreign_key="useresprit.id", nullable=True)
    support2_esprit_id: Optional[str] = Field(default=None, foreign_key="useresprit.id", nullable=True)
    
    # --- RELATIONSHIPS ---
    owned_esprits: List["UserEsprit"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

class UserEsprit(SQLModel, table=True):
    """Represents a specific instance of an Esprit owned by a user."""
    id: str = Field(primary_key=True, default_factory=lambda: __import__("uuid").uuid4().hex)
    owner_id: str = Field(foreign_key="user.user_id", index=True)
    esprit_data_id: str = Field(foreign_key="espritdata.esprit_id", index=True)
    current_hp: int
    current_level: int
    current_xp: int
    owner: Optional[User] = Relationship(back_populates="owned_esprits")
    esprit_data: Optional[EspritData] = Relationship(back_populates="owners")





