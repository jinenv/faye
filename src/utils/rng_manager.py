import random
from typing import Dict, List, Optional, Tuple

class RNGManager:
    """
    A utility class for managing random number generation, especially for weighted choices.
    """

    @staticmethod
    def weighted_choice(choices: Dict[str, float]) -> Optional[str]:
        """
        Selects a choice based on provided weights (probabilities).

        Args:
            choices (Dict[str, float]): A dictionary where keys are the choices
                                        and values are their corresponding probabilities/weights.
                                        Probabilities do not need to sum to 1.0; they will be normalized.

        Returns:
            str: The selected choice, or None if choices are empty or invalid.
        """
        if not choices:
            return None

        # Normalize weights (probabilities)
        total_weight = sum(choices.values())
        if total_weight == 0:
            # If all weights are zero, choose randomly (or return None if no valid choice)
            return random.choice(list(choices.keys())) if choices else None

        normalized_choices: List[Tuple[str, float]] = []
        for choice, weight in choices.items():
            normalized_choices.append((choice, weight / total_weight))

        # Sort choices by weight for easier cumulative sum calculation (optional, but good practice)
        normalized_choices.sort(key=lambda x: x[1])

        # Perform weighted selection
        rand_val = random.random() # A random float between 0.0 and 1.0
        cumulative_probability = 0.0

        for choice, probability in normalized_choices:
            cumulative_probability += probability
            if rand_val <= cumulative_probability:
                return choice

        # Fallback in case of floating point inaccuracies (should rarely happen)
        return normalized_choices[-1][0] if normalized_choices else None