# Nyxa Project To-Do List

A list of prioritized tasks for future development, covering both core game features and architectural improvements.

## 1. Core Feature Development

These tasks focus on building out the primary gameplay loop to drive user engagement.

### 1.1. Player & Esprit Progression System

-   [ ] **Define XP Curve:** Finalize the XP formula in `data/config/game_settings.json`. Define `xp_per_level_base` and `xp_per_level_multiplier`.
-   [ ] **Create Progression Utility:** Develop a new utility, e.g., `src/utils/progression_manager.py`, to handle all XP and level-up logic. This utility should be responsible for calculating level based on XP and vice-versa.
-   [ ] **Implement Stat Growth:** Define a formula for how an Esprit's stats increase upon leveling up. This could be a simple linear increase or based on a growth factor defined in `data/config/esprits.json`.
-   [ ] **Create Profile Command:** Add a `/profile` command that displays a user's level, XP, gold, dust, and their active Esprit's level and XP.

### 1.2. PvE Combat Loop

-   [ ] **Create Combat Cog:** Build a new `src/cogs/combat_cog.py`.
-   [ ] **Develop `/adventure` Command:** Implement the primary PvE command where a user's active Esprit fights a random wild Esprit from the `EspritData` table.
-   [ ] **Implement Turn-Based Logic:** Design the combat flow:
    -   Determine attack order based on the `base_speed` stat.
    -   Calculate damage (e.g., `ATK - DEF`).
    -   Incorporate other stats like `crit_rate` and `dodge_chance`.
-   [ ] **Integrate Rewards:** On victory, grant the user gold and call the progression utility to award XP to the user and their Esprit.
-   [ ] **(Optional) Interactive Combat:** Create a `CombatView(discord.ui.View)` with buttons for "Attack", "Use Item", "Flee" to make battles more interactive.

### 1.3. Item & Inventory System

-   [ ] **Define Item Models:** In `src/database/models.py`, create two new tables:
    -   `ItemData`: A static table defining all possible items (e.g., `item_id`, `name`, `description`, `effect`).
    -   `UserItem`: A table linking `user_id` to `item_id` with a `quantity` column.
-   [ ] **Expand Inventory Command:** Update the `/inventory` command in `src/cogs/economy_cog.py` to display both Esprits and Items. Consider pagination if the list becomes long.
-   [ ] **Add Items to Loot Tables:** Incorporate item drops as potential rewards from the `/adventure` command.

## 2. Architectural & Operational Improvements

These tasks focus on long-term project health, stability, and scalability.

### 2.1. Database Migrations

-   [ ] **Integrate Alembic:** Add `alembic` to `requirements.txt` and set it up to manage database schema changes.
-   [ ] **Generate Initial Migration:** Create the first migration script that reflects the current state of the models in `src/database/models.py`.
-   [ ] **Deprecate Destructive Resets:** Phase out the `/reset_db` command in favor of using Alembic migrations for all future database modifications. This is critical for retaining user data in a live environment.

### 2.2. Automated Testing

-   [ ] **Setup `pytest`:** Create a `tests/` directory and configure `pytest` and `pytest-asyncio`.
-   [ ] **Write Unit Tests:** Start by creating tests for your core utilities, such as `RNGManager` and the future `progression_manager.py`.
-   [ ] **Write Integration Tests:** Mock database sessions and Discord API responses to test the logic within your cogs. Ensure that commands fail gracefully with incorrect input.

### 2.3. User Experience (UX) Enhancements

-   [ ] **Paginated Inventory:** Refactor the `/inventory` command to use a paginated `discord.ui.View`, similar to the `/summon` command, especially as users accumulate many Esprits and items.
-   [ ] **More Visuals:** Leverage the `ImageGenerator` utility for more commands, such as generating an image for the `/profile` command or showing combat results visually.