# src/database/models.py
from typing import Optional, List
from datetime import datetime
import uuid
import sqlalchemy as sa
from sqlmodel import Field, SQLModel, Relationship

# LIMIT BREAK CONFIGURATION
PLAYER_LEVEL_THRESHOLDS = [
    (1, 20), (10, 30), (15, 50), (30, 75), (40, 100),
    (50, 135), (65, 150), (70, 175), (75, 200), (80, 200)
]

RARITY_LEVEL_CAPS = {
    "Common": 75,
    "Uncommon": 100,
    "Rare": 100,
    "Epic": 100,
    "Celestial": 150,
    "Supreme": 175,
    "Deity": 200
}

class EspritData(SQLModel, table=True):
    """Master data table for all Esprit types."""
    __tablename__ = "esprit_data"
    
    esprit_id: str = Field(primary_key=True, index=True)
    name: str = Field(index=True)  # For search queries
    description: str
    rarity: str = Field(index=True)  # For filtering by rarity
    class_name: str = Field(default="Unknown", index=True)  # For class-based queries
    visual_asset_path: str
    
    # Base stats - these scale with level and limit breaks
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
    
    # Relationships
    owners: List["UserEsprit"] = Relationship(
        back_populates="esprit_data",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

class User(SQLModel, table=True):
    """Stores data for each registered player."""
    __tablename__ = "users"
    
    user_id: str = Field(primary_key=True, index=True)
    username: str = Field(index=True)  # For leaderboards
    level: int = Field(default=1, index=True)  # For level-based queries
    xp: int = Field(default=0)
    
    # Currencies
    nyxies: int = Field(default=0, nullable=False)  # Primary currency
    moonglow: int = Field(default=0, nullable=False)  # Premium currency
    azurites: int = Field(default=0, nullable=False)  # Summoning currency
    azurite_shards: int = Field(default=0, nullable=False)  # Shard currency
    essence: int = Field(default=0, nullable=False)  # Upgrade currency
    aether: int = Field(default=0, nullable=False)  # Special currency
    loot_chests: int = Field(default=0, nullable=False)  # Reward containers
    
    # Daily claim tracking
    last_daily_claim: Optional[datetime] = Field(default=None, nullable=True)
    last_daily_summon: Optional[datetime] = Field(default=None, nullable=True)
    
    # Pity system counters
    pity_count_standard: int = Field(default=0, nullable=False)
    pity_count_premium: int = Field(default=0, nullable=False)
    
    # Team composition - store IDs only, resolve via relationships
    active_esprit_id: Optional[str] = Field(default=None, nullable=True)
    support1_esprit_id: Optional[str] = Field(default=None, nullable=True)
    support2_esprit_id: Optional[str] = Field(default=None, nullable=True)
    
    # Metadata
    created_at: datetime = Field(
        default=None, 
        sa_column=sa.Column(
            sa.DateTime(timezone=True), 
            nullable=False, 
            server_default=sa.func.current_timestamp()
        )
    )
    
    # Relationships
    owned_esprits: List["UserEsprit"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "foreign_keys": "[UserEsprit.owner_id]"
        }
    )
    
    def get_active_esprit(self) -> Optional["UserEsprit"]:
        """Get the currently active Esprit."""
        if not self.active_esprit_id:
            return None
        return next((e for e in self.owned_esprits if e.id == self.active_esprit_id), None)
    
    def get_support_esprits(self) -> List["UserEsprit"]:
        """Get support team Esprits."""
        support_ids = [self.support1_esprit_id, self.support2_esprit_id]
        return [e for e in self.owned_esprits if e.id in support_ids and e.id is not None]
    
    def get_player_base_cap(self) -> int:
        """Get base Esprit level cap based on player level."""
        base_cap = 20
        for required_level, cap in PLAYER_LEVEL_THRESHOLDS:
            if self.level >= required_level:
                base_cap = cap
        return base_cap
    
    def get_esprit_max_level(self, esprit_rarity: str) -> int:
        """Get maximum level an Esprit can reach."""
        player_base_cap = self.get_player_base_cap()
        rarity_absolute_cap = RARITY_LEVEL_CAPS.get(esprit_rarity, 100)
        return min(player_base_cap, rarity_absolute_cap)
    
    def xp_required_for_next_level(self) -> int:
        """XP needed to reach next player level."""
        if self.level >= 80:
            return 999999999  # Max level reached
        return int(100 * ((self.level + 1) ** 1.5))
    
    def can_level_up(self) -> bool:
        """Check if player can level up."""
        if self.level >= 80:
            return False
        total_xp_needed = sum(int(100 * (i ** 1.5)) for i in range(2, self.level + 2))
        return self.xp >= total_xp_needed
    
    def get_total_power(self) -> int:
        """Calculate total team power (active + supports)."""
        total = 0
        active = self.get_active_esprit()
        if active:
            total += active.calculate_power()
        
        for support in self.get_support_esprits():
            total += support.calculate_power()
        
        return total

    @staticmethod
    def get_esprit_max_level_for_level(player_level: int, esprit_rarity: str) -> int:
        """Static version for historical-level checks."""
        base_cap = 20
        for required_level, cap in PLAYER_LEVEL_THRESHOLDS:
            if player_level >= required_level:
                base_cap = cap

        rarity_absolute_cap = RARITY_LEVEL_CAPS.get(esprit_rarity, 100)
        return min(base_cap, rarity_absolute_cap)
    
    def check_and_apply_level_ups(self) -> dict:
        """Check if user can level up and apply levels automatically"""
        levels_gained = 0
        old_level = self.level
        
        while self.level < 80:  # Max level cap
            xp_needed = self.xp_required_for_next_level()
            if self.xp >= xp_needed:
                self.xp -= xp_needed
                self.level += 1
                levels_gained += 1
            else:
                break
        
        return {
            "levels_gained": levels_gained,
            "old_level": old_level,
            "new_level": self.level,
            "remaining_xp": self.xp
        }
    
class UserEsprit(SQLModel, table=True):
    """Represents a specific instance of an Esprit owned by a user."""
    __tablename__ = "user_esprits"
    
    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    owner_id: str = Field(foreign_key="users.user_id", index=True)
    esprit_data_id: str = Field(foreign_key="esprit_data.esprit_id", index=True)
    
    # Current state
    current_hp: int
    current_level: int = Field(default=1, index=True)  # For level-based queries
    current_xp: int = Field(default=0)
    
    # Limit break tracking
    limit_breaks_performed: int = Field(default=0)
    stat_boost_multiplier: float = Field(default=1.0)  # Cumulative limit break bonuses
    
    # Metadata
    acquired_at: datetime = Field(
        default=None,
        sa_column=sa.Column(
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp()
        )
    )
    
    # Relationships
    owner: Optional[User] = Relationship(
        back_populates="owned_esprits",
        sa_relationship_kwargs={"foreign_keys": "[UserEsprit.owner_id]"}
    )
    esprit_data: Optional[EspritData] = Relationship(back_populates="owners")

    def calculate_stat(self, stat_name: str) -> int:
        """Calculate stat with level scaling and limit break bonuses."""
        if not self.esprit_data:
            return 0
        
        base_stat = getattr(self.esprit_data, f"base_{stat_name.lower()}", 0)
        if base_stat == 0:
            return 0
        
        # Level scaling: +5% per level
        level_multiplier = 1 + (self.current_level - 1) * 0.05
        
        # Apply limit break stat bonuses
        final_value = base_stat * level_multiplier * self.stat_boost_multiplier
        return max(1, int(final_value))  # Ensure minimum value of 1

    def calculate_power(self) -> int:
        """Calculate total combat power (Sigil)."""
        if not self.esprit_data:
            return 0
        
        # Weighted power calculation
        power = (
            (self.calculate_stat('hp') / 4) +
            (self.calculate_stat('attack') * 2.5) +
            (self.calculate_stat('defense') * 2.5) +
            (self.calculate_stat('speed') * 3.0) +
            (self.calculate_stat('magic_resist') * 2.0) +
            (self.esprit_data.base_crit_rate * 500) +
            (self.esprit_data.base_block_rate * 500) +
            (self.esprit_data.base_dodge_chance * 600) +
            (self.esprit_data.base_mana * 0.5) +
            (self.esprit_data.base_mana_regen * 100)
        )
        
        # Rarity multipliers
        rarity_multipliers = {
            "Common": 1.0, 
            "Uncommon": 1.1, 
            "Rare": 1.25, 
            "Epic": 1.4, 
            "Celestial": 1.6, 
            "Supreme": 1.8, 
            "Deity": 2.0
        }
        
        rarity_mult = rarity_multipliers.get(self.esprit_data.rarity, 1.0)
        final_power = int(power * rarity_mult)
        
        return max(1, final_power)  # Ensure minimum power of 1
    
    def get_current_level_cap(self) -> int:
        """Get current level cap based on player level progression."""
        if not self.owner or not self.esprit_data:
            return 20
        
        # Player level determines current cap
        player_cap = self.owner.get_player_base_cap()
        
        # Rarity determines absolute maximum
        rarity_max = RARITY_LEVEL_CAPS.get(self.esprit_data.rarity, 100)
        
        # Current cap is the lower of player progression or rarity maximum
        return min(player_cap, rarity_max)
    
    def can_level_up(self) -> bool:
        """Check if Esprit can level up normally."""
        if self.current_level >= self.get_current_level_cap():
            return False
        return self.current_xp >= self.xp_required_for_next_level()
    
    def xp_required_for_next_level(self) -> int:
        """XP needed for next level."""
        if self.current_level >= 200:
            return 999999999  # Max level reached
        return int(50 * ((self.current_level + 1) ** 1.3))
    
    def level_up(self) -> dict:
        """Level up the Esprit and return results."""
        if not self.can_level_up():
            return {"success": False, "reason": "Cannot level up"}
        
        old_power = self.calculate_power()
        old_level = self.current_level
        
        # Consume XP and level up
        xp_cost = self.xp_required_for_next_level()
        self.current_xp -= xp_cost
        self.current_level += 1
        
        # Update HP to new maximum
        self.current_hp = self.calculate_stat('hp')
        
        new_power = self.calculate_power()
        
        return {
            "success": True,
            "old_level": old_level,
            "new_level": self.current_level,
            "old_power": old_power,
            "new_power": new_power,
            "power_increase": new_power - old_power,
            "xp_consumed": xp_cost,
            "remaining_xp": self.current_xp
        }
    
    def can_limit_break(self) -> dict:
        """Check if Esprit can perform a limit break."""
        if not self.owner or not self.esprit_data:
            return {"can_break": False, "reason": "Missing data"}
        
        # Get current player-based cap
        current_player_cap = self.owner.get_player_base_cap()
        rarity_max = RARITY_LEVEL_CAPS.get(self.esprit_data.rarity, 100)
        
        # Must be at current player cap to limit break
        if self.current_level < current_player_cap:
            return {
                "can_break": False, 
                "reason": "not_at_cap",
                "current_cap": current_player_cap,
                "current_level": self.current_level,
                "levels_needed": current_player_cap - self.current_level
            }
        
        # Check if there's a higher threshold available within rarity limits
        player_level = self.owner.level
        next_threshold = None
        
        # Find next available threshold
        for required_level, cap in PLAYER_LEVEL_THRESHOLDS:
            if cap > current_player_cap and player_level >= required_level and cap <= rarity_max:
                next_threshold = cap
                break
        
        # If no next threshold available
        if not next_threshold:
            if current_player_cap >= rarity_max:
                return {"can_break": False, "reason": "at_rarity_maximum", "rarity_max": rarity_max}
            else:
                return {"can_break": False, "reason": "insufficient_player_level"}
        
        return {
            "can_break": True,
            "current_cap": current_player_cap,
            "next_cap": next_threshold,
            "levels_to_unlock": next_threshold - current_player_cap,
            "cost": self.get_limit_break_cost()
        }
    
    def get_limit_break_cost(self) -> dict:
        """Calculate materials needed for limit break using config values."""
        if not self.esprit_data:
            return {"essence": 0, "moonglow": 0}
        
        # Use config values
        base_essence = 200  # From config: limit_break_system.base_costs.essence
        base_moonglow = 500  # From config: limit_break_system.base_costs.moonglow
        
        # Rarity multipliers from config
        rarity_multipliers = {
            "Common": 1.0, "Uncommon": 1.5, "Rare": 2.0, "Epic": 3.0,
            "Celestial": 5.0, "Supreme": 7.0, "Deity": 10.0
        }
        
        # Level scaling: base_cost * rarity_multiplier * (1 + esprit_level / 50)
        level_multiplier = 1 + (self.current_level / 50)
        rarity_mult = rarity_multipliers.get(self.esprit_data.rarity, 1.0)
        
        # Previous limit breaks: 50% increase each (1.5^breaks)
        limit_break_multiplier = 1.5 ** self.limit_breaks_performed
        
        total_multiplier = rarity_mult * level_multiplier * limit_break_multiplier
        
        return {
            "essence": int(base_essence * total_multiplier),
            "moonglow": int(base_moonglow * total_multiplier),
            "multiplier_breakdown": {
                "rarity": rarity_mult,
                "level": level_multiplier,
                "previous_breaks": limit_break_multiplier,
                "total": total_multiplier
            }
        }
    
    def perform_limit_break(self) -> dict:
        """Perform limit break using player progression system."""
        limit_check = self.can_limit_break()
        if not limit_check["can_break"]:
            return {"success": False, "reason": limit_check["reason"]}
        
        old_power = self.calculate_power()
        old_multiplier = self.stat_boost_multiplier
        old_cap = self.get_current_level_cap()
        
        # Apply 10% stat boost
        self.stat_boost_multiplier *= 1.1
        self.limit_breaks_performed += 1
        
        # Heal to new max HP
        self.current_hp = self.calculate_stat('hp')
        
        new_power = self.calculate_power()
        new_cap = self.get_current_level_cap()
        
        return {
            "success": True,
            "old_power": old_power,
            "new_power": new_power,
            "power_increase": new_power - old_power,
            "old_level_cap": old_cap,
            "new_level_cap": new_cap,
            "levels_unlocked": new_cap - old_cap,
            "total_limit_breaks": self.limit_breaks_performed,
            "old_stat_multiplier": old_multiplier,
            "new_stat_multiplier": self.stat_boost_multiplier,
            "stat_multiplier": self.stat_boost_multiplier,
            "stat_increase_percent": 10.0
        }
    
    def get_display_info(self) -> dict:
        """Get formatted info for display purposes."""
        if not self.esprit_data:
            return {}
        
        return {
            "name": self.esprit_data.name,
            "rarity": self.esprit_data.rarity,
            "class": self.esprit_data.class_name,
            "level": self.current_level,
            "level_cap": self.get_current_level_cap(),
            "power": self.calculate_power(),
            "stats": {
                "hp": self.calculate_stat('hp'),
                "attack": self.calculate_stat('attack'),
                "defense": self.calculate_stat('defense'),
                "speed": self.calculate_stat('speed'),
                "magic_resist": self.calculate_stat('magic_resist')
            },
            "limit_breaks": self.limit_breaks_performed,
            "stat_multiplier": round(self.stat_boost_multiplier, 2),
            "can_level_up": self.can_level_up(),
            "can_limit_break": self.can_limit_break()["can_break"]
        }


# Database indexes for performance at scale
class DatabaseIndexes:
    """
    Additional indexes to add for performance optimization:
    
    CREATE INDEX idx_user_esprits_power ON user_esprits USING btree (owner_id, current_level DESC);
    CREATE INDEX idx_users_leaderboard ON users USING btree (level DESC, xp DESC);
    CREATE INDEX idx_esprit_data_rarity_class ON esprit_data USING btree (rarity, class_name);
    CREATE INDEX idx_user_esprits_acquired ON user_esprits USING btree (acquired_at DESC);
    CREATE INDEX idx_users_daily_claims ON users USING btree (last_daily_claim);
    """
    pass


