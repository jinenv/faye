# Game Balance Calculations

**This document is deprecated for specific formulas and values.**

To align with our **Single Source of Truth** principle, all game balance calculations are now defined by a combination of two authoritative sources:

1.  **The Data Source:** `data/config/game_settings.json`
    - This file contains all the raw numbers, weights, multipliers, costs, and rewards that drive the game's economy and progression systems.

2.  **The Logic Source:** `src/database/models.py`
    - The methods on the `User` and `UserEsprit` models contain the Python implementation of the formulas that use the values from the configuration file.

Please refer directly to these two files for the most current and accurate information on all game calculations.