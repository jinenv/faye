# src/utils/progression_manager.py
import math
from typing import Dict, Any

def get_player_xp_for_next_level(current_level: int, progression_cfg: dict) -> int:
    """XP needed to reach the next player level."""
    if current_level >= progression_cfg.get("player_max_level", 100):
        return 0
    xp_curve = progression_cfg.get("player_xp_curve", {"base": 100, "exponent": 1.5})
    base = xp_curve.get("base", 100)
    exponent = xp_curve.get("exponent", 1.5)
    return int(base * (current_level ** exponent))

def add_player_xp(user, amount, progression_cfg: dict):
    """
    Adds XP to a user, handles multiple level-ups.
    Modifies user object in place.
    Returns (leveled_up: bool, old_level: int, new_level: int)
    """
    max_level = progression_cfg.get("player_max_level", 100)
    base = progression_cfg.get("player_xp_curve", {}).get("base", 100)
    exponent = progression_cfg.get("player_xp_curve", {}).get("exponent", 1.5)

    leveled_up = False
    old_level = user.level

    while user.level < max_level:
        xp_needed = int(base * (user.level ** exponent))
        if user.xp + amount < xp_needed:
            user.xp += amount
            return leveled_up, old_level, user.level
        leveled_up = True
        amount = (user.xp + amount) - xp_needed
        user.level += 1
        user.xp = 0
    user.xp = 0
    return leveled_up, old_level, user.level

def get_esprit_max_level_for_level(player_level: int, rarity: str, progression_cfg: dict) -> int:
    """
    Given player level and rarity, returns the *current* max level for an esprit.
    """
    thresholds = progression_cfg.get("player_level_thresholds", [])
    base_cap = 20
    for th in thresholds:
        if player_level >= th["player_level"]:
            base_cap = th["base_esprit_cap"]
    rarity_caps = progression_cfg.get("rarity_level_caps", {})
    rarity_cap = rarity_caps.get(rarity, 100)
    return min(base_cap, rarity_cap)

def get_rarity_level_cap(rarity: str, progression_cfg: dict) -> int:
    """Returns the absolute max cap for a rarity."""
    return progression_cfg.get("rarity_level_caps", {}).get(rarity, 100)

def get_max_limit_breaks(rarity: str, progression_cfg: dict, lb_cfg: dict) -> int:
    """
    Returns the max number of limit breaks possible for this rarity, using config.
    Assumes each break increases cap by lb_cfg['cap_increase_per_break'] (default: 20).
    """
    base_cap = 20
    rarity_caps = progression_cfg.get("rarity_level_caps", {})
    max_level = rarity_caps.get(rarity, 100)
    cap_increase = lb_cfg.get("cap_increase_per_break", 20)
    return max(0, (max_level - base_cap) // cap_increase)

def get_limit_break_cost(esprit_level: int, rarity: str, prev_breaks: int, progression_cfg: dict, lb_cfg: dict) -> dict:
    """
    Returns the cost for the next limit break for an esprit.
    All config-driven.
    """
    base_costs = lb_cfg.get("base_costs", {"remna": 200, "virelite": 500})
    rarity_multipliers = lb_cfg.get("rarity_cost_multipliers", {})
    level_scaling_factor = lb_cfg.get("level_scaling_factor", 50)
    prev_breaks_multiplier = lb_cfg.get("previous_breaks_multiplier", 1.5)

    rarity_mult = rarity_multipliers.get(rarity, 1.0)
    level_multiplier = 1 + (esprit_level / level_scaling_factor)
    break_multiplier = prev_breaks_multiplier ** prev_breaks

    multiplier = rarity_mult * level_multiplier * break_multiplier

    return {
        "remna": int(base_costs.get("remna", 200) * multiplier),
        "virelite": int(base_costs.get("virelite", 500) * multiplier),
    }

def can_limit_break(esprit, user, progression_cfg: dict, lb_cfg: dict) -> dict:
    """
    Returns a dict: {can_break: bool, reason: str}
    esprit = UserEsprit instance (must have esprit_data)
    user = User instance (must have level)
    """
    if not esprit or not esprit.esprit_data or not user:
        return {"can_break": False, "reason": "Missing data"}

    current_cap = get_esprit_max_level_for_level(user.level, esprit.esprit_data.rarity, progression_cfg)
    rarity_cap = get_rarity_level_cap(esprit.esprit_data.rarity, progression_cfg)

    if esprit.current_level < current_cap:
        return {"can_break": False, "reason": "not_at_cap"}
    if current_cap >= rarity_cap:
        return {"can_break": False, "reason": "at_rarity_maximum"}

    # Find the next cap (after player levels up)
    thresholds = progression_cfg.get("player_level_thresholds", [])
    next_cap = None
    for th in thresholds:
        if user.level < th["player_level"]:
            next_cap = th["base_esprit_cap"]
            break
    if next_cap is None or next_cap <= current_cap:
        return {"can_break": False, "reason": "insufficient_player_level"}

    # Limit break cap (absolute)
    max_breaks = get_max_limit_breaks(esprit.esprit_data.rarity, progression_cfg, lb_cfg)
    if esprit.limit_breaks_performed >= max_breaks:
        return {"can_break": False, "reason": "max_limit_breaks"}

    return {"can_break": True}

def esprit_power_calc(esprit, progression_cfg: dict, stat_cfg: dict, power_cfg: dict) -> int:
    """
    Calculates esprit power, config-driven.
    Expects esprit = UserEsprit instance (with esprit_data attached).
    """
    if not esprit or not esprit.esprit_data:
        return 0
    weights = power_cfg.get("sigil_weights", {})
    def stat(stat_name):
        base = getattr(esprit.esprit_data, f"base_{stat_name}", 0)
        level_mult = 1 + (esprit.current_level - 1) * stat_cfg.get("level_multiplier_per_level", 0.05)
        lb_mult = esprit.stat_boost_multiplier or 1.0
        return base * level_mult * lb_mult

    power = (
        stat('hp') * weights.get('hp', 0.25) +
        stat('attack') * weights.get('attack', 2.5) +
        stat('defense') * weights.get('defense', 2.5) +
        stat('speed') * weights.get('speed', 3.0) +
        stat('magic_resist') * weights.get('magic_resist', 2.0) +
        esprit.esprit_data.base_crit_rate * weights.get('crit_rate', 500) +
        esprit.esprit_data.base_block_rate * weights.get('block_rate', 500) +
        esprit.esprit_data.base_dodge_chance * weights.get('dodge', 600) +
        esprit.esprit_data.base_mana * weights.get('mana', 0.5) +
        esprit.esprit_data.base_mana_regen * weights.get('mana_regen', 100)
    )

    rarity_mult = power_cfg.get("rarity_multipliers", {}).get(esprit.esprit_data.rarity, 1.0)
    return max(1, int(power * rarity_mult))

