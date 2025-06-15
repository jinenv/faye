# src/database/models.py
from typing import Optional, List, Dict
from datetime import datetime
import sqlalchemy as sa
from sqlmodel import Field, SQLModel, Relationship
from nanoid import generate

def generate_nanoid():
    """Generates a short, unique ID."""
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
    level_cap: int = Field(default=10, nullable=False) # The player's current max level
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

    # --- Player Progression Methods ---
    def get_xp_for_next_level(self, progression_cfg: dict) -> int:
        """Calculates the total XP required to reach the next player level."""
        if self.level >= self.level_cap:
            return 0
        xp_curve = progression_cfg.get("player_xp_curve", {"base": 100, "exponent": 1.5})
        return int(xp_curve['base'] * (self.level ** xp_curve['exponent']))

    def add_xp(self, amount: int, progression_cfg: dict) -> tuple[bool, int]:
        """Adds XP, handles multiple level-ups, and returns (did_level_up, levels_gained)."""
        if self.level >= self.level_cap:
            return False, 0

        leveled_up = False
        levels_gained = 0
        self.xp += amount
        
        xp_needed = self.get_xp_for_next_level(progression_cfg)
        while xp_needed > 0 and self.xp >= xp_needed and self.level < self.level_cap:
            self.level += 1
            self.xp -= xp_needed
            leveled_up = True
            levels_gained += 1
            xp_needed = self.get_xp_for_next_level(progression_cfg)
        
        # Clamp XP at max level for the current cap
        if self.level >= self.level_cap:
            self.xp = 0

        return leveled_up, levels_gained
    
    def get_next_trial_info(self, progression_cfg: dict) -> Optional[Dict]:
        """Finds the next available trial for the user based on their level."""
        trial_tiers = progression_cfg.get("player_trial_tiers", [])
        # Find the first trial that unlocks at a level higher than the player's current level
        next_trial = next((tier for tier in trial_tiers if tier.get("unlocks_at_level", 999) > self.level), None)
        return next_trial

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
    esprit_data: Optional[EspritData] = Relationship(back_populates="owners")

    # --- Esprit Progression & Calculation Methods ---
    def get_level_cap(self, progression_cfg: dict) -> int:
        """Calculates this Esprit's current maximum level based on its owner's level and its rarity."""
        if not self.owner or not self.esprit_data: return 10
        
        thresholds = progression_cfg.get("player_level_thresholds", [])
        player_cap = 10
        for th in thresholds:
            if self.owner.level >= th["player_level"]:
                player_cap = th["base_esprit_cap"]
        
        rarity_cap = progression_cfg.get("rarity_level_caps", {}).get(self.esprit_data.rarity, 100)
        return min(player_cap, rarity_cap)

    def can_limit_break(self, progression_cfg: dict) -> dict:
        """Checks if this Esprit is eligible for a limit break."""
        if not self.owner or not self.esprit_data:
            return {"can_break": False, "reason": "Missing owner or Esprit data"}

        current_cap = self.get_level_cap(progression_cfg)
        if self.current_level < current_cap:
            return {"can_break": False, "reason": "Not at level cap"}
            
        rarity_cap = progression_cfg.get("rarity_level_caps", {}).get(self.esprit_data.rarity, 100)
        if current_cap >= rarity_cap:
             return {"can_break": False, "reason": "At absolute rarity maximum"}
        
        return {"can_break": True, "reason": "Ready to limit break"}

    def get_limit_break_cost(self, lb_cfg: dict) -> dict:
        """Calculates the cost for the next limit break."""
        if not self.esprit_data: return {"remna": 999999, "virelite": 999999}
        
        base_costs = lb_cfg.get("base_costs", {})
        rarity_mult = lb_cfg.get("rarity_cost_multipliers", {}).get(self.esprit_data.rarity, 1.0)
        level_mult = 1 + (self.current_level / lb_cfg.get("level_scaling_factor", 50))
        break_mult = lb_cfg.get("previous_breaks_multiplier", 1.5) ** self.limit_breaks_performed
        
        total_multiplier = rarity_mult * level_mult * break_mult
        
        return {
            "remna": int(base_costs.get("remna", 200) * total_multiplier),
            "virelite": int(base_costs.get("virelite", 500) * total_multiplier),
        }

    def calculate_stat(self, stat_name: str, stat_cfg: dict) -> int:
        """Calculates a single stat based on level, limit breaks, and configs."""
        if not self.esprit_data: return 0
        
        base_stat = getattr(self.esprit_data, f"base_{stat_name.lower()}", 0)
        if base_stat == 0: return 0

        level_multiplier = 1 + (self.current_level - 1) * stat_cfg.get("level_multiplier_per_level", 0.05)
        
        final_value = base_stat * level_multiplier * self.stat_boost_multiplier
        return max(1, int(final_value))

    def calculate_power(self, power_cfg: dict, stat_cfg: dict) -> int:
        """Calculates the total Sigil Power of the Esprit."""
        if not self.esprit_data: return 0
        
        weights = power_cfg.get("sigil_weights", {})
        power = (
            (self.calculate_stat('hp', stat_cfg) * weights.get('hp', 0.25)) +
            (self.calculate_stat('attack', stat_cfg) * weights.get('attack', 2.5)) +
            (self.calculate_stat('defense', stat_cfg) * weights.get('defense', 2.5)) +
            (self.calculate_stat('speed', stat_cfg) * weights.get('speed', 3.0)) +
            (self.calculate_stat('magic_resist', stat_cfg) * weights.get('magic_resist', 2.0)) +
            (self.esprit_data.base_crit_rate * weights.get('crit_rate', 500)) +
            (self.esprit_data.base_block_rate * weights.get('block_rate', 500)) +
            (self.esprit_data.base_dodge_chance * weights.get('dodge', 600)) +
            (self.esprit_data.base_mana * weights.get('mana', 0.5)) +
            (self.esprit_data.base_mana_regen * weights.get('mana_regen', 100))
        )
        
        rarity_mult = power_cfg.get("rarity_multipliers", {}).get(self.esprit_data.rarity, 1.0)
        return max(1, int(power * rarity_mult))


