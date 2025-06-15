# src/utils/rng_manager.py

import random
from typing import Dict, Optional, Union, List

class RNGManager:
    """
    Provides methods for handling various types of randomization,
    including weighted choices and dice rolls.
    """

    @staticmethod
    def get_random_in_range(value: Union[int, List[int]]) -> int:
        """
        Calculates a random integer from a given value.
        - If value is an integer, it returns the integer itself.
        - If value is a list of two integers [min, max], it returns a
          random integer within that inclusive range.
        
        Args:
            value: The value from the config, either a number or a [min, max] list.

        Returns:
            A calculated integer.
        """
        if isinstance(value, int):
            return value
        if isinstance(value, list) and len(value) == 2:
            return random.randint(value[0], value[1])
        
        # Fallback for misconfigured values, returning 0
        return 0

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
        # Edge-case rounding
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
