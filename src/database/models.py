# src/database/models.py
from typing import Optional, List
from datetime import datetime
import sqlalchemy as sa
from sqlmodel import Field, SQLModel, Relationship

# This model is unchanged
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
    nyxies: int = Field(default=0, nullable=False)
    moonglow: int = Field(default=0, nullable=False)
    azurites: int = Field(default=0, nullable=False) 
    azurite_shards: int = Field(default=0, nullable=False)
    essence: int = Field(default=0, nullable=False)
    aether: int = Field(default=0, nullable=False)
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
    active_esprit_id: Optional[str] = Field(default=None, foreign_key="useresprit.id", nullable=True)
    support1_esprit_id: Optional[str] = Field(default=None, foreign_key="useresprit.id", nullable=True)
    support2_esprit_id: Optional[str] = Field(default=None, foreign_key="useresprit.id", nullable=True)
    
    # --- RELATIONSHIP FIX IS HERE ---
    # We now explicitly tell this relationship which foreign key to use
    # on the UserEsprit table to find its children.
    owned_esprits: List["UserEsprit"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "foreign_keys": "[UserEsprit.owner_id]" 
        }
    )
    
    def get_esprit_max_level(self) -> int:
        """Get the maximum esprit level based on player level and limit break thresholds"""
        # Define limit break thresholds
        thresholds = [
            {"player_level": 1, "esprit_max": 10},
            {"player_level": 10, "esprit_max": 20},
            {"player_level": 20, "esprit_max": 40},
            {"player_level": 30, "esprit_max": 60},
            {"player_level": 40, "esprit_max": 100},
            {"player_level": 50, "esprit_max": 150},
            {"player_level": 60, "esprit_max": 240}
        ]
        
        # Find the appropriate threshold
        max_level = self.level  # Default if no threshold found
        for threshold in reversed(thresholds):
            if self.level >= threshold["player_level"]:
                max_level = threshold["esprit_max"]
                break
        
        return max_level

class UserEsprit(SQLModel, table=True):
    """Represents a specific instance of an Esprit owned by a user."""
    id: str = Field(primary_key=True, default_factory=lambda: __import__("uuid").uuid4().hex)
    owner_id: str = Field(foreign_key="user.user_id", index=True)
    esprit_data_id: str = Field(foreign_key="espritdata.esprit_id", index=True)
    current_hp: int
    current_level: int
    current_xp: int
    
    # --- RELATIONSHIP FIX IS HERE ---
    # We also tell this side of the relationship how to find its parent.
    owner: Optional[User] = Relationship(
        back_populates="owned_esprits",
        sa_relationship_kwargs={
            "foreign_keys": "[UserEsprit.owner_id]"
        }
    )
    esprit_data: Optional[EspritData] = Relationship(back_populates="owners")

    def calculate_power(self) -> int:
        """Calculate total combat power of this Esprit"""
        if not self.esprit_data:
            return 0
        
        level_multiplier = 1 + (self.current_level - 1) * 0.05
        
        # Base stats with level scaling
        hp = self.esprit_data.base_hp * level_multiplier
        attack = self.esprit_data.base_attack * level_multiplier
        defense = self.esprit_data.base_defense * level_multiplier
        speed = self.esprit_data.base_speed * level_multiplier
        
        # Weight different stats
        power = int(
            hp * 0.3 +
            attack * 0.35 +
            defense * 0.25 +
            speed * 0.1
        )
        
        # Rarity multiplier
        rarity_multipliers = {
            "Common": 1.0,
            "Uncommon": 1.2,
            "Rare": 1.5,
            "Epic": 2.0,
            "Celestial": 2.5,
            "Supreme": 3.0,
            "Deity": 4.0
        }
        power = int(power * rarity_multipliers.get(self.esprit_data.rarity, 1.0))
        
        return power
    
    def calculate_stat(self, stat_name: str) -> int:
        """Calculate a specific stat with level scaling"""
        if not self.esprit_data:
            return 0
        
        level_multiplier = 1 + (self.current_level - 1) * 0.05
        base_stat = getattr(self.esprit_data, f"base_{stat_name.lower()}", 0)
        return int(base_stat * level_multiplier)
    
    def can_level_up(self, player_level: int) -> bool:
        """Check if this esprit can level up based on player's level and limit breaks"""
        # Get the owner's limit break threshold
        thresholds = [
            {"player_level": 1, "esprit_max": 10},
            {"player_level": 10, "esprit_max": 20},
            {"player_level": 20, "esprit_max": 40},
            {"player_level": 30, "esprit_max": 60},
            {"player_level": 40, "esprit_max": 100},
            {"player_level": 50, "esprit_max": 150},
            {"player_level": 60, "esprit_max": 240}
        ]
        
        max_allowed = player_level  # Default
        for threshold in reversed(thresholds):
            if player_level >= threshold["player_level"]:
                max_allowed = threshold["esprit_max"]
                break
        
        return self.current_level < max_allowed



