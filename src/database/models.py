from typing import Optional
from sqlmodel import Field, SQLModel

class User(SQLModel, table=True):
    """
    Represents a user's profile in the database.
    This will store their chosen class, and later other progression data.
    """
    user_id: str = Field(primary_key=True) # Discord User ID
    username: str = Field(index=True) # Discord Username
    class_name: Optional[str] = Field(default=None) # The chosen class (e.g., "Dwarf", "Elf")
    # Add other fields here as your project progresses (level, gold, inventory, etc.)
    # Example:
    # level: int = Field(default=1)
    # gold: int = Field(default=0)
    # last_daily_claim: Optional[datetime] = Field(default=None)

# You might later add other models here for Companions, Inventory items, etc.