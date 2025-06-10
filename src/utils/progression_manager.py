# src/utils/progression_manager.py
import math

from src.utils.config_manager import ConfigManager
from src.database.models import User, UserEsprit, EspritData

class ProgressionManager:
    """
    Handles all player and Esprit progression logic, including XP requirements,
    leveling, and stat calculations.
    """
    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager.get_config("data/config/game_settings") or {}
        self.prog_config = self.config.get("progression", {})
        
        self.player_max_level = self.prog_config.get("player_max_level", 100)
        self.esprit_max_level = self.prog_config.get("esprit_max_level", 100)
        
        self.player_xp_curve = self.prog_config.get("player_xp_curve", {"base": 100, "exponent": 1.5})
        self.esprit_xp_curve = self.prog_config.get("esprit_xp_curve", {"base": 50, "exponent": 1.3})
        
        self.esprit_upgrade_cost_per_level = self.prog_config.get("esprit_upgrade_cost_per_level", 10)

    def get_player_xp_for_next_level(self, current_level: int) -> int:
        """Calculates the total XP required to reach the next player level."""
        if current_level >= self.player_max_level:
            return 0
        base = self.player_xp_curve.get('base', 100)
        exponent = self.player_xp_curve.get('exponent', 1.5)
        return int(base * (current_level ** exponent))

    def get_esprit_xp_for_next_level(self, current_level: int) -> int:
        """Calculates the total XP required to reach the next Esprit level."""
        if current_level >= self.esprit_max_level:
            return 0
        base = self.esprit_xp_curve.get('base', 50)
        exponent = self.esprit_xp_curve.get('exponent', 1.3)
        return int(base * (current_level ** exponent))

    def get_esprit_upgrade_cost(self, current_level: int) -> int:
        """Calculates the Moonglow cost to upgrade an Esprit to the next level."""
        if current_level >= self.esprit_max_level:
            return 0
        return (current_level + 1) * self.esprit_upgrade_cost_per_level

    def add_player_xp(self, player: User, amount: int) -> tuple[User, bool]:
        """
        Adds XP to a player and checks for level-up.
        Returns the updated player and a boolean indicating if a level-up occurred.
        """
        if player.level >= self.player_max_level:
            return player, False

        leveled_up = False
        player.xp += amount
        xp_needed = self.get_player_xp_for_next_level(player.level)

        while xp_needed > 0 and player.xp >= xp_needed:
            player.level += 1
            player.xp -= xp_needed
            leveled_up = True
            xp_needed = self.get_player_xp_for_next_level(player.level)
            if player.level >= self.player_max_level:
                player.xp = 0
                break

        return player, leveled_up

    # NOTE: The logic for leveling up Esprits (recalculate_esprit_stats, etc.)
    # will be more complex and should be built out when we implement the 
    # `/esprit upgrade` command, as it needs to handle stat growth, rarity modifiers, etc.
    # The current functions provide a solid base for that future work.