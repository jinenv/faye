# src/database/models.py
from typing import Optional, List
from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel, Relationship


class EspritData(SQLModel, table=True):
    esprit_id: str = Field(primary_key=True, index=True)
    name: str
    description: str
    rarity: str
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
    user_id: str = Field(primary_key=True, index=True)
    username: str

    level: int
    xp: int
    gold: int
    dust: int = 0

    last_daily_claim: Optional[datetime] = Field(default=None, nullable=True)
    active_esprit_id: Optional[str] = Field(default=None, nullable=True)

    created_at: datetime = Field(
        default=None,
        sa_column=sa.Column(
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp()
        )
    )

    owned_esprits: List["UserEsprit"] = Relationship(back_populates="owner")


class UserEsprit(SQLModel, table=True):
    id: str = Field(primary_key=True, default_factory=lambda: __import__("uuid").uuid4().hex)
    owner_id: str = Field(foreign_key="user.user_id", index=True)
    esprit_data_id: str = Field(foreign_key="espritdata.esprit_id", index=True)

    current_hp: int
    current_level: int
    current_xp: int

    owner: Optional[User] = Relationship(back_populates="owned_esprits")
    esprit_data: Optional[EspritData] = Relationship(back_populates="owners")





