# src/database/models.py
from typing import Optional, List
from datetime import datetime
import sqlalchemy as sa
from sqlmodel import Field, SQLModel, Relationship

class EspritData(SQLModel, table=True):
    # ... no changes here ...
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
    nyxies: int = Field(default=0, nullable=False)
    moonglow: int = Field(default=0, nullable=False)
    azurites: int = Field(default=0, nullable=False) 
    azurite_shards: int = Field(default=0, nullable=False)
    essence: int = Field(default=0, nullable=False)
    aether: int = Field(default=0, nullable=False)
    loot_chests: int = Field(default=0, nullable=False)
    last_daily_claim: Optional[datetime] = Field(default=None, nullable=True)
    last_daily_summon: Optional[datetime] = Field(default=None, nullable=True)
    
    # Pity counters are now part of the model
    pity_count_standard: int = Field(default=0, nullable=False)
    pity_count_premium: int = Field(default=0, nullable=False)

    created_at: datetime = Field(default=None, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()))
    active_esprit_id: Optional[str] = Field(default=None, foreign_key="useresprit.id", nullable=True)
    support1_esprit_id: Optional[str] = Field(default=None, foreign_key="useresprit.id", nullable=True)
    support2_esprit_id: Optional[str] = Field(default=None, foreign_key="useresprit.id", nullable=True)
    
    owned_esprits: List["UserEsprit"] = Relationship(back_populates="owner", sa_relationship_kwargs={"cascade": "all, delete-orphan", "foreign_keys": "[UserEsprit.owner_id]"})
    
    def get_esprit_max_level(self) -> int:
        # ... this function remains the same ...
        pass

class UserEsprit(SQLModel, table=True):
    """Represents a specific instance of an Esprit owned by a user."""
    id: str = Field(primary_key=True, default_factory=lambda: __import__("uuid").uuid4().hex)
    owner_id: str = Field(foreign_key="user.user_id", index=True)
    esprit_data_id: str = Field(foreign_key="espritdata.esprit_id", index=True)
    current_hp: int
    current_level: int
    current_xp: int
    
    owner: Optional[User] = Relationship(back_populates="owned_esprits", sa_relationship_kwargs={"foreign_keys": "[UserEsprit.owner_id]"})
    esprit_data: Optional[EspritData] = Relationship(back_populates="owners")

    def calculate_stat(self, stat_name: str) -> int:
        if not self.esprit_data: return 0
        level_multiplier = 1 + (self.current_level - 1) * 0.05
        base_stat = getattr(self.esprit_data, f"base_{stat_name.lower()}", 0)
        return int(base_stat * level_multiplier)

    def calculate_power(self) -> int:
        """
        Calculate total combat power ('Sigil') of this Esprit based on a 
        detailed formula that includes all primary and secondary stats.
        """
        if not self.esprit_data: return 0
        
        # This new formula is inspired by your spreadsheet for a more accurate power level.
        power = (
            (self.calculate_stat('hp') / 4) +
            (self.calculate_stat('attack') * 2.5) +
            (self.calculate_stat('defense') * 2.5) +
            (self.calculate_stat('speed') * 3.0) +
            (self.calculate_stat('magic_resist') * 2.0) +
            (self.esprit_data.base_crit_rate * 500) +
            (self.esprit_data.base_block_rate * 500) +
            (self.esprit_data.base_dodge_chance * 600)
        )
        
        rarity_multipliers = {"Common": 1.0, "Uncommon": 1.1, "Rare": 1.25, "Epic": 1.4, "Celestial": 1.6, "Supreme": 1.8, "Deity": 2.0}
        return int(power * rarity_multipliers.get(self.esprit_data.rarity, 1.0))
        
    def can_level_up(self, player_level: int) -> bool:
        # ... this function remains the same ...
        pass


