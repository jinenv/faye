# src/services/limit_break_service.py
from typing import Dict, List
from sqlmodel import Session
from src.database.models import User, UserEsprit

class LimitBreakService:
    """Handles all limit break operations."""

    @staticmethod
    def attempt_limit_break(session: Session, user: User, esprit: UserEsprit) -> Dict:
        # 1. Validate eligibility
        can_break = esprit.can_limit_break()
        if not can_break["can_break"]:
            return {"success": False, "reason": can_break["reason"], "details": can_break}

        # 2. Calculate cost & check resources
        cost = esprit.get_limit_break_cost()
        if user.essence < cost["essence"]:
            return {"success": False, "reason": "insufficient_essence", "required": cost["essence"], "available": user.essence}
        if user.moonglow < cost["moonglow"]:
            return {"success": False, "reason": "insufficient_moonglow", "required": cost["moonglow"], "available": user.moonglow}

        # 3. Deduct materials
        user.essence -= cost["essence"]
        user.moonglow -= cost["moonglow"]

        # 4. Perform the break
        result = esprit.perform_limit_break()
        if result.get("success"):
            session.add(user)
            session.add(esprit)
            session.commit()
            result["cost_paid"] = cost
            result["message"] = f"🔓 LIMIT BREAK! {esprit.esprit_data.name} transcends their limits!"

        return result

    @staticmethod
    def check_player_level_up_limit_breaks(session: Session, user: User, old_level: int) -> List[Dict]:
        """Notify which Esprits gained a higher cap when the player leveled."""
        notifications: List[Dict] = []
        for esprit in user.owned_esprits:
            if not esprit.esprit_data:
                continue

            old_cap = User.get_esprit_max_level_for_level(old_level, esprit.esprit_data.rarity)
            new_cap = User.get_esprit_max_level_for_level(user.level, esprit.esprit_data.rarity)
            if new_cap > old_cap:
                can_immediately = (
                    esprit.current_level < new_cap
                    and esprit.current_xp >= esprit.xp_required_for_next_level()
                )
                notifications.append({
                    "esprit_name": esprit.esprit_data.name,
                    "esprit_id": esprit.id,
                    "old_cap": old_cap,
                    "new_cap": new_cap,
                    "levels_unlocked": new_cap - old_cap,
                    "can_immediately_level": can_immediately
                })

        return notifications

    @staticmethod
    def get_limit_break_preview(user: User, esprit: UserEsprit) -> Dict:
        """Show cost, stat boosts, and power increase without applying."""
        if not esprit.esprit_data:
            return {"error": "No Esprit data"}

        can_break = esprit.can_limit_break()
        if not can_break["can_break"]:
            return can_break

        # Current vs boosted stats
        stats = {
            stat: esprit.calculate_stat(stat)
            for stat in ("hp", "attack", "defense", "speed", "magic_resist")
        }
        boosted = {stat: int(val * 1.1) for stat, val in stats.items()}

        current_power = esprit.calculate_power()
        estimated = int(current_power * 1.1)
        cost = esprit.get_limit_break_cost()

        return {
            "can_break": True,
            "current_level": esprit.current_level,
            "current_cap": can_break["current_cap"],
            "new_cap": can_break["next_cap"],
            "levels_to_unlock": can_break["levels_to_unlock"],
            "current_stats": stats,
            "boosted_stats": boosted,
            "stat_increases": {stat: boosted[stat] - stats[stat] for stat in stats},
            "current_power": current_power,
            "estimated_new_power": estimated,
            "power_increase": estimated - current_power,
            "cost": cost,
            "can_afford": user.essence >= cost["essence"] and user.moonglow >= cost["moonglow"]
        }
