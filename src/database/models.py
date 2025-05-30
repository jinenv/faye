from typing import Optional, List
from datetime import datetime
import uuid # For generating unique IDs for UserEsprit instances

from sqlmodel import Field, Relationship, SQLModel # Import Relationship for linking models

# --- User Model ---
class User(SQLModel, table=True):
    """
    Represents a player's profile in the database.
    """
    user_id: str = Field(primary_key=True) # Discord User ID (e.g., "123456789012345678")
    username: str = Field(index=True) # Discord Username (e.g., "PlayerName#1234")
    level: int = Field(default=1)
    xp: int = Field(default=0)
    gold: int = Field(default=0)
    last_daily_claim: Optional[datetime] = Field(default=None) # Timestamp for daily claim cooldown

    # Optional: Link to the active Esprit. This uses a foreign key to UserEsprit.id
    active_esprit_id: Optional[uuid.UUID] = Field(default=None, foreign_key="useresprit.id")

    # Define a relationship to access a user's owned Esprits
    # This was fixed in the previous step
    esprits: List["UserEsprit"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"foreign_keys": "UserEsprit.owner_id"} # Explicitly link via owner_id
    )


# --- Esprit Data Model (Definitions of all possible Esprits) ---
class EspritData(SQLModel, table=True):
    """
    Represents the static, defined data for a type of Esprit.
    This is what 'Common Dog' or 'Goddess Waifu' IS.
    """
    esprit_id: str = Field(primary_key=True) # Unique ID for this type of Esprit (e.g., "common_dog", "goddess_waifu")
    name: str
    description: str
    rarity: str # e.g., "Common", "Rare", "Ultra Rare"
    visual_asset_path: str # Path to the Esprit's sprite file (e.g., "assets/esprits/common_dog.png")

    # Base Stats for this Esprit type
    base_hp: int
    base_attack: int
    base_defense: int
    base_speed: int
    base_magic_resist: int = Field(default=0)
    base_crit_rate: float = Field(default=0.05)
    base_block_rate: float = Field(default=0.0)
    base_dodge_chance: float = Field(default=0.0)
    base_mana_regen: int = Field(default=0)
    base_mana: int = Field(default=0)
    
    def to_dict(self):
        """Converts the EspritData instance to a dictionary, useful for image rendering."""
        return {
            "esprit_id": self.esprit_id,
            "name": self.name,
            "description": self.description,
            "rarity": self.rarity,
            "visual_asset_path": self.visual_asset_path,
            "base_hp": self.base_hp,
            "base_attack": self.base_attack,
            "base_defense": self.base_defense,
            "base_speed": self.base_speed,
            "base_magic_resist": self.base_magic_resist,
            "base_crit_rate": self.base_crit_rate,
            "base_block_rate": self.base_block_rate,
            "base_dodge_chance": self.base_dodge_chance,
            "base_mana_regen": self.base_mana_regen,
        }


# --- User Esprit Model (Player-owned Esprit Instances) ---
class UserEsprit(SQLModel, table=True):
    """
    Represents a specific Esprit instance owned by a player.
    This tracks its individual progress and equipped items.
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True) # Unique ID for this specific Esprit instance

    owner_id: str = Field(foreign_key="user.user_id") # Link to the User who owns this Esprit
    # --- CRITICAL FIX IS HERE ---
    owner: Optional[User] = Relationship(
        back_populates="esprits",
        sa_relationship_kwargs={"foreign_keys": "UserEsprit.owner_id"} # Explicitly link via owner_id
    )
    # --- END CRITICAL FIX ---

    esprit_data_id: str = Field(foreign_key="espritdata.esprit_id") # Link to the EspritData definition

    # Current Stats (can change based on level, equipment, buffs)
    current_hp: int
    current_level: int = Field(default=1)
    current_xp: int = Field(default=0)