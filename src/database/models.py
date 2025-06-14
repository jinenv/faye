# src/database/models.py
from typing import Optional, List, Dict
from datetime import datetime
import uuid
import sqlalchemy as sa
from sqlmodel import Field, SQLModel, Relationship

# These constants are now just FALLBACKS. The primary source of truth is game_settings.json.
PLAYER_LEVEL_THRESHOLDS = [
    (1, 20), (10, 30), (15, 50), (30, 75), (40, 100),
    (50, 135), (65, 150), (70, 175), (75, 200), (80, 200)
]

RARITY_LEVEL_CAPS = {
    "Common": 75, "Uncommon": 100, "Rare": 100, "Epic": 100,
    "Celestial": 150, "Supreme": 175, "Deity": 200
}

class EspritData(SQLModel, table=True):
    __tablename__ = "esprit_data"
    esprit_id: str = Field(primary_key=True, index=True)
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
    owners: List["UserEsprit"] = Relationship(back_populates="esprit_data", sa_relationship_kwargs={"cascade": "all, delete-orphan"})

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
    created_at: datetime = Field(default=None, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()))
    owned_esprits: List["UserEsprit"] = Relationship(back_populates="owner", sa_relationship_kwargs={"cascade": "all, delete-orphan", "foreign_keys": "[UserEsprit.owner_id]"})

    def get_player_base_cap(self, progression_config: Dict) -> int:
        thresholds = progression_config.get("player_level_thresholds", [])
        if not thresholds:  # Fallback to hardcoded if config is missing
            return max((cap for req_lvl, cap in PLAYER_LEVEL_THRESHOLDS if self.level >= req_lvl), default=20)
        
        # Use config data
        base_cap = 20
        for threshold in thresholds:
            if self.level >= threshold["player_level"]:
                base_cap = threshold["base_esprit_cap"]
        return base_cap

class UserEsprit(SQLModel, table=True):
    __tablename__ = "user_esprits"
    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    owner_id: str = Field(foreign_key="users.user_id", index=True)
    esprit_data_id: str = Field(foreign_key="esprit_data.esprit_id", index=True)
    current_hp: int
    current_level: int = Field(default=1, index=True)
    # current_xp is now removed from the model as it's obsolete.
    limit_breaks_performed: int = Field(default=0)
    stat_boost_multiplier: float = Field(default=1.0)
    acquired_at: datetime = Field(default=None, sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()))
    owner: Optional[User] = Relationship(back_populates="owned_esprits", sa_relationship_kwargs={"foreign_keys": "[UserEsprit.owner_id]"})
    esprit_data: Optional[EspritData] = Relationship(back_populates="owners")

    def calculate_stat(self, stat_name: str, stat_config: Dict) -> int:
        if not self.esprit_data: return 0
        
        base_stat = getattr(self.esprit_data, f"base_{stat_name.lower()}", 0)
        if base_stat == 0: return 0

        # Use formula from config, with a safe fallback
        level_mult_per_level = stat_config.get("level_multiplier_per_level", 0.05)
        level_multiplier = 1 + (self.current_level - 1) * level_mult_per_level
        
        # This is already correctly compounded in the limitbreak command.
        final_value = base_stat * level_multiplier * self.stat_boost_multiplier
        return max(1, int(final_value))

    def calculate_power(self, power_config: Dict, stat_config: Dict) -> int:
        if not self.esprit_data: return 0
        
        weights = power_config.get("sigil_weights", {})
        
        power = (
            (self.calculate_stat('hp', stat_config) * weights.get('hp', 0.25)) +
            (self.calculate_stat('attack', stat_config) * weights.get('attack', 2.5)) +
            (self.calculate_stat('defense', stat_config) * weights.get('defense', 2.5)) +
            (self.calculate_stat('speed', stat_config) * weights.get('speed', 3.0)) +
            (self.calculate_stat('magic_resist', stat_config) * weights.get('magic_resist', 2.0)) +
            (self.esprit_data.base_crit_rate * weights.get('crit_rate', 500)) +
            (self.esprit_data.base_block_rate * weights.get('block_rate', 500)) +
            (self.esprit_data.base_dodge_chance * weights.get('dodge', 600)) +
            (self.esprit_data.base_mana * weights.get('mana', 0.5)) +
            (self.esprit_data.base_mana_regen * weights.get('mana_regen', 100))
        )
        
        rarity_multipliers = power_config.get("rarity_multipliers", {})
        rarity_mult = rarity_multipliers.get(self.esprit_data.rarity, 1.0)
        
        return max(1, int(power * rarity_mult))

    def get_current_level_cap(self, progression_config: Dict) -> int:
        if not self.owner or not self.esprit_data: return 20
        
        player_cap = self.owner.get_player_base_cap(progression_config)
        rarity_caps = progression_config.get("rarity_level_caps", RARITY_LEVEL_CAPS)
        rarity_max = rarity_caps.get(self.esprit_data.rarity, 100)
        
        return min(player_cap, rarity_max)

    def can_limit_break(self, progression_config: Dict) -> dict:
        if not self.owner or not self.esprit_data:
            return {"can_break": False, "reason": "Missing data"}

        current_cap = self.get_current_level_cap(progression_config)
        
        if self.current_level < current_cap:
            return {"can_break": False, "reason": "not_at_cap"}
            
        rarity_caps = progression_config.get("rarity_level_caps", RARITY_LEVEL_CAPS)
        rarity_max = rarity_caps.get(self.esprit_data.rarity, 100)
        if current_cap >= rarity_max:
             return {"can_break": False, "reason": "at_rarity_maximum"}
        
        # This part checks if the player's *next* possible cap is the same as the current one.
        # This implies they need to level up their player account to unlock the next tier.
        thresholds = progression_config.get("player_level_thresholds", [])
        next_possible_cap = current_cap
        for threshold in thresholds:
            if self.owner.level >= threshold["player_level"]:
                next_possible_cap = threshold["base_esprit_cap"]
        
        if next_possible_cap <= current_cap:
             return {"can_break": False, "reason": "insufficient_player_level"}
        
        return {"can_break": True}

    def get_limit_break_cost(self, lb_config: Dict) -> dict:
        if not self.esprit_data: return {"remna": 0, "virelite": 0}
        
        base_costs = lb_config.get("base_costs", {})
        base_remna = base_costs.get("remna", 200)
        base_virelite = base_costs.get("virelite", 500)
        
        rarity_multipliers = lb_config.get("rarity_cost_multipliers", {})
        level_scaling_factor = lb_config.get("level_scaling_factor", 50) # Matching formula: esprit_level / 50
        prev_breaks_multiplier = lb_config.get("previous_breaks_multiplier", 1.5)
        
        rarity_mult = rarity_multipliers.get(self.esprit_data.rarity, 1.0)
        level_multiplier = 1 + (self.current_level / level_scaling_factor)
        limit_break_multiplier = prev_breaks_multiplier ** self.limit_breaks_performed
        
        total_multiplier = rarity_mult * level_multiplier * limit_break_multiplier
        
        return {
            "remna": int(base_remna * total_multiplier),
            "virelite": int(base_virelite * total_multiplier),
        }


