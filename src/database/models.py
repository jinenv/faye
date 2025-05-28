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
    # We define this as a relationship here, but the active_esprit_id field would be on User.
    # For simplicity in models, we often link via ID and manage the relationship in code.
    # Let's keep it simple for now, just the ID.
    active_esprit_id: Optional[uuid.UUID] = Field(default=None, foreign_key="useresprit.id")

    # Define a relationship to access a user's owned Esprits
    esprits: List["UserEsprit"] = Relationship(back_populates="owner")


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
    base_magic_resist: int = Field(default=0) # New stat based on your examples
    base_crit_rate: float = Field(default=0.05) # 5% base crit rate
    base_block_rate: float = Field(default=0.0) # 0% base block rate
    base_dodge_chance: float = Field(default=0.0) # 0% base dodge chance
    base_mana_regen: int = Field(default=0) # New stat based on your examples

    # Relationship to actual instances of this Esprit type owned by players
    # Note: This is commented out for now as we primarily query EspritData directly
    # and link UserEsprit to EspritData.esprit_id. If we needed to find all
    # UserEsprits of a specific EspritData, this would be useful.
    # instances: List["UserEsprit"] = Relationship(back_populates="esprit_definition")


# --- User Esprit Model (Player-owned Esprit Instances) ---
class UserEsprit(SQLModel, table=True):
    """
    Represents a specific Esprit instance owned by a player.
    This tracks its individual progress and equipped items.
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True) # Unique ID for this specific Esprit instance

    owner_id: str = Field(foreign_key="user.user_id") # Link to the User who owns this Esprit
    owner: Optional[User] = Relationship(back_populates="esprits") # Define relationship back to owner

    esprit_data_id: str = Field(foreign_key="espritdata.esprit_id") # Link to the EspritData definition
    # esprit_definition: Optional[EspritData] = Relationship(back_populates="instances") # See note in EspritData

    # Current Stats (can change based on level, equipment, buffs)
    current_hp: int
    current_level: int = Field(default=1)
    current_xp: int = Field(default=0)

    # We'll calculate current attack, defense, etc. dynamically from base stats + level + equipment
    # equipped_item_id: Optional[uuid.UUID] = Field(default=None, foreign_key="useritem.id") # Link to equipped item (future)

    # You can add more fields here as you expand features:
    # equipped_items: List["UserItem"] = Relationship(link_model=UserEspritEquipmentLink) # For multiple equipment slots
    # abilities: List[str] = Field(default_factory=list) # List of ability IDs this instance has


# Example of a many-to-many link model for equipment (future expansion)
# class UserEspritEquipmentLink(SQLModel, table=True):
#     user_esprit_id: uuid.UUID = Field(foreign_key="useresprit.id", primary_key=True)
#     user_item_id: uuid.UUID = Field(foreign_key="useritem.id", primary_key=True)
#     slot: str # e.g., "weapon", "armor", "accessory"