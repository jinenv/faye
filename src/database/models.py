# src/database/models.py
from typing import Optional, List
from datetime import datetime
import sqlalchemy as sa
from sqlmodel import Field, SQLModel, Relationship
from nanoid import generate

def generate_nanoid():
    return generate(size=6)

class EspritData(SQLModel, table=True):
    __tablename__ = "esprit_data"
    esprit_id: str = Field(default_factory=generate_nanoid, primary_key=True, index=True)
    name: str = Field(index=True)
    description: str
    rarity: str = Field(index=True)
    class_name: str = Field(default="Unknown", index=True)
    visual_asset_path: str
    base_hp: int
    base_attack: int
    base_defense: int
    base_speed: float
    base_magic_resist: int = 0
    base_crit_rate: float = 0.0
    base_block_rate: float = 0.0
    base_dodge_chance: float = 0.0
    base_mana_regen: float = 0.0
    base_mana: int = 0
    owners: List["UserEsprit"] = Relationship(
        back_populates="esprit_data",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

class User(SQLModel, table=True):
    __tablename__ = "users"
    user_id: str = Field(primary_key=True, index=True)
    username: str = Field(index=True)
    level: int = Field(default=1, index=True)
    xp: int = Field(default=0)
    faylen: int = Field(default=0, nullable=False)
    virelite: int = Field(default=0, nullable=False)
    fayrites: int = Field(default=0, nullable=False)
    fayrite_shards: int = Field(default=0, nullable=False)
    remna: int = Field(default=0, nullable=False)
    ethryl: int = Field(default=0, nullable=False)
    loot_chests: int = Field(default=0, nullable=False)
    last_daily_claim: Optional[datetime] = Field(default=None, nullable=True)
    last_daily_summon: Optional[datetime] = Field(default=None, nullable=True)
    pity_count_standard: int = Field(default=0, nullable=False)
    pity_count_premium: int = Field(default=0, nullable=False)
    active_esprit_id: Optional[str] = Field(default=None, nullable=True)
    support1_esprit_id: Optional[str] = Field(default=None, nullable=True)
    support2_esprit_id: Optional[str] = Field(default=None, nullable=True)
    created_at: datetime = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp())
    )
    owned_esprits: List["UserEsprit"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "foreign_keys": "[UserEsprit.owner_id]"}
    )

class UserEsprit(SQLModel, table=True):
    __tablename__ = "user_esprits"
    id: str = Field(default_factory=generate_nanoid, primary_key=True)
    owner_id: str = Field(foreign_key="users.user_id", index=True)
    esprit_data_id: str = Field(foreign_key="esprit_data.esprit_id", index=True)
    current_hp: int
    current_level: int = Field(default=1, index=True)
    limit_breaks_performed: int = Field(default=0)
    stat_boost_multiplier: float = Field(default=1.0)
    locked: bool = Field(default=False, nullable=False)
    acquired_at: datetime = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp())
    )
    owner: Optional[User] = Relationship(
        back_populates="owned_esprits",
        sa_relationship_kwargs={"foreign_keys": "[UserEsprit.owner_id]"}
    )
    esprit_data: Optional[EspritData] = Relationship(
        back_populates="owners"
    )


