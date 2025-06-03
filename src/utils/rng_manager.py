import random
from typing import Dict, List, Optional, Tuple


class RNGManager:
    """
    Handles weighted-random selections for NyxaBot.
    Designed so `SummonCog` can call
        self.rng_manager.get_random_rarity(weights, luck_modifier=0.05)
    without exploding.
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        # Local RNG instance so tests can seed deterministically.
        self._rng = random.Random(seed)

    # ──────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────
    def _normalize(
        self, choices: Dict[str, float]
    ) -> List[Tuple[str, float]]:
        """Return list of (key, normalized_weight)."""
        if not choices:
            return []

        total = sum(choices.values())
        if total == 0:
            # All weights zero → fallback to uniform distribution.
            uniform = 1.0 / len(choices)
            return [(k, uniform) for k in choices]

        return [(k, w / total) for k, w in choices.items()]

    def _weighted_pick(self, choices: Dict[str, float]) -> Optional[str]:
        """
        Core weighted-random routine.  
        `choices` can be raw or already normalized; we normalize anyway.
        """
        pool = self._normalize(choices)
        if not pool:
            return None

        rand_val = self._rng.random()  # 0.0–1.0
        cumulative = 0.0
        for key, prob in pool:
            cumulative += prob
            if rand_val <= cumulative:
                return key
        # Edge-case float spill-over
        return pool[-1][0]

    # ──────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────
    def weighted_choice(self, choices: Dict[str, float]) -> Optional[str]:
        """Public wrapper around `_weighted_pick` (kept for backward compat)."""
        return self._weighted_pick(choices)

    def get_random_rarity(
        self,
        rarity_weights: Dict[str, float],
        *,
        luck_modifier: float = 0.0,
    ) -> Optional[str]:
        """
        Main entry point for SummonCog.

        Args
        ----
        rarity_weights : dict[str, float]
            Raw probabilities (they need **not** sum to 1).
        luck_modifier  : float (default 0.0)
            Positive values increase the weight of *all* rarities,
            but you can plug in more complex luck formulas later.

        Returns
        -------
        str | None
            Selected rarity, or None if `rarity_weights` is empty/invalid.
        """
        if not rarity_weights:
            return None

        if luck_modifier:
            rarity_weights = {
                k: max(v * (1.0 + luck_modifier), 0.0)
                for k, v in rarity_weights.items()
            }

        return self._weighted_pick(rarity_weights)
