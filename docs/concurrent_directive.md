# Nyxa / Faye – Unified Directive & State Architecture
**Document Version:** 4.0 (Post-Hardening)
**Last Updated:** 2025-06-14

This is the authoritative specification for every AI or human contributor. If new work contradicts this file, this file must be updated first.

---
### 1 • Architectural Guarantees (The Nyxa Way)
*These principles are the foundation of our codebase and must never be broken.*

- **G1. Modularity:** Features are encapsulated in Cogs (`src/cogs/`). Shared utilities reside in `src/utils/`. UI components like Views are organized in `src/views/` or within their respective cogs.

- **G2. Single-Location Logic:** Core calculations and business logic (e.g., stat calculations, upgrade costs, level caps) **must** live on the database model classes in `src/database/models.py`. Cogs **must** call these model methods and not reimplement logic.

- **G3. Config-Driven Values:** All tunable values, formulas, and parameters that affect game balance (e.g., rewards, costs, cooldowns, version numbers) **must** be defined in `data/config/game_settings.json`. Cogs will load these values at runtime via the central `ConfigManager`. **There must be no hardcoded magic numbers in the cogs.**

- **G4. Explicit Transactional Logging:** All state-changing events (e.g., currency changes, item grants, esprit creation/destruction) **must** be logged to the dedicated `transactions.log` file. This is achieved by adding a function to `src/utils/transaction_logger.py` and calling it from the relevant cog *after* the database session is successfully committed.

- **G5. Universal Rate Limiting:** All user-facing application commands **must** be protected by a `RateLimiter` instance defined in their cog. This is a non-negotiable requirement to ensure bot stability and prevent user-side spam.

- **G6. Session Discipline:** Use one `AsyncSession` per command context via the `async with get_session():` context manager. The session object may be passed to helper functions but new sessions must not be created mid-command.

- **G7. Heavy CPU Work in Executors:** Any process that is CPU-bound (e.g., complex image generation) **must** be run in an executor thread pool to keep the bot's event loop from blocking.

---
### 2 • Current System Status & Verified Accomplishments

The following cogs and systems have been reviewed, hardened, and confirmed to be in compliance with the architectural guarantees as of the last update:

#### ✅ **Core Infrastructure**
- **Logging:** A dual-logging system is in place. General bot logs are written to `bot.log`, while all economic and state-changing events are recorded in `transactions.log` via the `transaction_logger.py` utility.
- **Configuration:** `ConfigManager` correctly serves as the single point of access for all game settings.
- **Database:** `SQLModel` is correctly implemented with a central `get_session` manager.

#### ✅ **Hardened Cogs**
- **`admin_cog`**: The gold standard. Features explicit transactional logging for admin actions and correctly sources its data.
- **`economy_cog`**: Fully rate-limited. All daily claims and crafting events are now recorded in the transaction log.
- **`onboarding_cog`**: The new user `/start` transaction is logged in detail. Code has been refactored to be fully dynamic based on the `starter_currencies` config.
- **`summon_cog`**: Now fully rate-limited. All summons (free and paid) are recorded in the transaction log. Esprit rarity pools are now cached to reduce database load.
- **`esprit_cog`**: Fully rate-limited across all commands. All key transactions (`upgrade`, `limitbreak`, `dissolve`) are logged. Power calculations in the collection view are now consistent with all other commands, sourcing their formulas directly from the game config.
- **`utility_cog`**: Fully rate-limited. All formerly hardcoded information is now correctly sourced from `game_settings.json`.

---
### 3 • Key System Specifications

#### **The Single Source of Truth**
- **For Logic & Formulas:** The methods on the model classes in `src/database/models.py`.
- **For Values & Parameters:** The configuration dictionaries within `data/config/game_settings.json`.
- **For Documentation:** This `concurrent_directive.md` document.

*Any file that contradicts these sources (e.g., `calculations.md`) is considered deprecated.*

---
### 4 • Next Development Priorities

With the core systems hardened, the development priorities are now focused on new gameplay features.

#### **HIGH PRIORITY - Gameplay Loop**
1.  **Combat System Implementation:**
    - **Task:** Design and build the `combat_cog`. This includes turn-based logic, skill/ability systems, and combat rewards.
    - **Action:** Ensure all combat rewards (XP, currency, items) are granted via methods that include transactional logging.
2.  **Economic Balancing & Analysis:**
    - **Task:** Analyze the `transactions.log` to tune the game economy.
    - **Action:** Review the rates of currency generation (dailies, dissolving, combat) versus currency sinks (upgrading, limit breaking, summoning) to ensure a balanced and engaging player experience.

#### **MEDIUM PRIORITY - Database & Polish**
1.  **Database Migration: Remove `current_xp`**
    - **Task:** The `current_xp` column on the `user_esprits` table is obsolete and must be removed.
    - **Action:** Execute the Alembic migration process (`revision` -> `edit` -> `upgrade head`) to drop this column from the database schema.
2.  **UI Consistency Pass:**
    - **Task:** Perform a final pass on all bot embeds and messages.
    - **Action:** Ensure consistent terminology ("Sigil," "Moonglow"), clear formatting, and helpful error messages across the entire bot.

---
### 5 • Pre-Merge & Deployment Checklist
*A final check before any new feature branch is merged into production.*

- [ ] **Guarantees Upheld:** The new code adheres to all principles in Section 1.
- [ ] **Config Driven:** All new tunable values have been added to `game_settings.json`.
- [ ] **Single-Location Logic:** New calculations are implemented on the data models in `models.py`.
- [ ] **Transactional Logging:** All new state-changing actions are logged via `transaction_logger.py`.
- [ ] **Rate-Limited:** All new user-facing commands are rate-limited.
- [ ] **Alembic Vetted:** If the change required a database migration, the generated script has been manually reviewed and is reversible if possible.
- [ ] **Successful Boot:** The bot starts without errors.
