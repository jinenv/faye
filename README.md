# Nyxa AI Developer & Operations Manual
**Document Version:** 2.0
**Status:** Post-Hardening, Pre-Combat

## 1. Core Mandate

The primary directive for any AI interacting with this repository is to assist in the development and maintenance of the Nyxa bot while **strictly adhering to the established architectural principles outlined below.** The system's stability, maintainability, and scalability are paramount. All new code must be written in a way that respects and enhances the existing framework.

## 2. The Single Source of Truth

This project operates on a strict "Single Source of Truth" model. This is the most important concept to understand before making any changes.

- **For Game Logic & Formulas:** All game balance calculations (e.g., stat growth, power calculation, upgrade costs) are exclusively defined as methods on the data models in `src/database/models.py`. **DO NOT** replicate this logic in any cog.
- **For Game Values & Parameters:** All tunable values (e.g., currency amounts, chances, cooldowns, version numbers) are exclusively defined in `data/config/game_settings.json`. These are loaded at runtime via the `ConfigManager`.
- **For Logging & Auditing:** All significant state changes are logged via the helper functions in `src/utils/transaction_logger.py`.
- **For Project Direction:** This `README.md` serves as the official record of the project's architecture and goals.

Any file that contradicts these sources (e.g., `docs/calculations.md`) is considered **deprecated**.

## 3. Architectural Guarantees (The Nyxa Way)

These rules are non-negotiable and have been confirmed across the codebase.

- **G1. Modularity:** Code is encapsulated in `src/cogs/`. Shared tools are in `src/utils/`.
- **G2. Single-Location Logic:** Cogs call methods on models from `models.py`; they do not contain business logic.
- **G3. Config-Driven:** No hardcoded values. All tunable parameters are in `game_settings.json`.
- **G4. Structured Transactional Logging:** All state-changing events MUST be logged as a JSON object to `transactions.log` via the `transaction_logger.py` utility. General operational logs go to `bot.log`.
- **G5. Universal Rate-Limiting:** All user-facing commands MUST be protected by a `RateLimiter` instance to ensure stability.
- **G6. Session Discipline:** All database interactions MUST use the `async with get_session():` context manager.
- **G7. Code Consistency:** New code must match the style, patterns, and structure of the existing hardened cogs (e.g., `esprit_cog.py`).

## 4. Verified Systems & Current State

The startup sequence is confirmed to be clean with no errors. The following systems and cogs have been reviewed, hardened, and confirmed to be in compliance with all architectural guarantees:

#### ✅ **Core Infrastructure**
- **Logging:** A dual-logging system is in place. General bot logs are written to `bot.log`, while all economic and state-changing events are recorded as structured JSON in `transactions.log`.
- **Configuration:** `ConfigManager` correctly serves as the single point of access for all game settings.
- **Database:** `SQLModel` is correctly implemented with a central `get_session` manager. The database schema is up to date, with legacy columns successfully removed.

#### ✅ **Hardened Cogs**
- **`admin_cog`**: The standard for administrative command implementation.
- **`economy_cog`**: Fully rate-limited and logs all transactions to the JSON audit trail.
- **`esprit_cog`**: Fully rate-limited across all commands and logs all asset transformations. Caching is implemented for collection queries, and power calculations are fully config-driven and consistent.
- **`onboarding_cog`**: Logs new user acquisition to the JSON audit trail and is fully dynamic from config.
- **`summon_cog`**: Fully rate-limited and logs all summons to the JSON audit trail. Uses caching to reduce DB load.
- **`utility_cog`**: Fully rate-limited, and all display information is sourced from the config.

## 5. Key Utilities & Usage Patterns

To contribute to this project, use the established utilities as follows.

#### Rate Limiting a Command

    # At the start of any slash command function:
    if not await self.rate_limiter.check(str(interaction.user.id)):
        wait = await self.rate_limiter.get_cooldown(str(interaction.user.id))
        return await interaction.followup.send(f"You're acting too fast! Please wait {wait}s.", ephemeral=True)

#### Adding a New Transactional Log

1.  Open `src/utils/transaction_logger.py`.
2.  Create a new, specific function for the event (e.g., `log_combat_reward`).
3.  Inside the function, construct a `log_data` dictionary containing `timestamp`, `event_type`, `user_id`, `username`, and a nested `details` dictionary with event-specific information.
4.  Log the dictionary using `tx_logger.info(json.dumps(log_data))`.
5.  Call this new function from your cog *after* the `session.commit()` call.

## 6. Current Development Priorities

The foundational work is complete. Development should now focus on the primary gameplay loop.

- **HIGH PRIORITY: Combat System Implementation**
    - **Task:** Design and build the `combat_cog`. This will involve turn-based logic, a skill/ability system, and generating combat rewards (XP, currency, items).
    - **Watch Out For:** All damage formulas and reward tables must be config-driven. All rewards granted must be logged via the `transaction_logger`.

- **MEDIUM PRIORITY: Economic Analysis & Balancing**
    - **Task:** Begin analyzing the `transactions.log` file to tune the game economy.
    - **Action:** Use the structured log data to query and aggregate how much currency is entering and leaving the game. This will inform balance changes to `game_settings.json` to ensure a rewarding and sustainable player experience.

- **LOW PRIORITY: UI/UX Polish**
    - **Task:** Perform a pass on all bot embeds and messages.
    - **Action:** Ensure consistent terminology, clear formatting, and helpful error messages across the entire bot.