# src/utils/rng_manager.py

import random
from typing import Dict, Optional


class RNGManager:
    """
    Provides a method to pick a weighted rarity.
    Expects something like: {"Common": 0.5, "Uncommon": 0.25, …}
    """

    @staticmethod
    def _normalize(choices: Dict[str, float]) -> Dict[str, float]:
        total = sum(choices.values())
        if total <= 0:
            raise ValueError("Sum of weights must be > 0")
        return {k: v / total for k, v in choices.items()}

    @staticmethod
    def _weighted_pick(choices: Dict[str, float]) -> Optional[str]:
        """
        Given a dict of {item_name: weight}, return one item_name at random
        according to the weights. Returns None if choices is empty.
        """
        if not choices:
            return None

        norm = RNGManager._normalize(choices)
        r = random.random()
        cumulative = 0.0
        for name, weight in norm.items():
            cumulative += weight
            if r <= cumulative:
                return name
        # Edge‐case rounding
        return next(reversed(norm), None)

    def get_random_rarity(
        self,
        rarity_weights: Dict[str, float],
        luck_modifier: float = 0.0
    ) -> Optional[str]:
        """
        rarity_weights: {"Common": 0.50, "Uncommon": 0.25, …}
        luck_modifier: add this to each weight before normalizing (if desired).
        """
        if not rarity_weights:
            return None

        # Apply luck_modifier (if nonzero) uniformly to each tier
        if luck_modifier != 0:
            adjusted: Dict[str, float] = {}
            for k, v in rarity_weights.items():
                new_weight = v + luck_modifier
                # don't allow negative
                adjusted[k] = max(new_weight, 0.0)
            return self._weighted_pick(adjusted)

        return self._weighted_pick(rarity_weights)
