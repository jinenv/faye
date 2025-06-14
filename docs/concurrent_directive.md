# Nyxa / Faye – Unified Directive & State Architecture
**Document Version:** 3.0
**Last Updated:** 2025-06-13

This is the authoritative specification for every AI or human contributor. If new work contradicts this file, this file must be updated first.

---
### 1 • Architectural Guarantees (The Nyxa Way)
*These principles must never be broken.*

- **G1. Modularity:** Features are encapsulated in Cogs (`src/cogs/`). Shared utilities reside in `src/utils/`. UI components like Views are organized in `src/views/`.
- **G2. Single-Location Logic:** Core calculations and business logic **must** live on the database model classes in `src/database/models.py`. Cogs should call these methods, not reimplement logic.
- **G3. Config-Driven:** All tunable values, formulas, and parameters that affect game balance **must** be in configuration files (`data/config/*.json`). Load these values via the central `ConfigManager` at runtime. **No hardcoded magic numbers.**
- **G4. Session Discipline:** Use one `AsyncSession` per command context. Pass the session object to helper functions; do not create new ones mid-command.
- **G5. Rate Limiting:** Apply the `RateLimiter` to any command that can be spammed to consume resources or clog the event loop.
- **G6. Heavy CPU Work in Executors:** Any process that is CPU-bound (e.g., complex image generation) **must** be run in an executor thread pool to keep the bot's event loop from blocking.
- **G7. Alembic Discipline:** Follow a strict workflow: `alembic revision --autogenerate` → **Manually review the generated script for correctness** → `alembic upgrade head`.

---
### 2 • Current System Status & Verified Accomplishments

#### ✅ **Completed & Verified**
- **Core Systems:** Python 3.12, discord.py 2.3.2, SQLModel, and Alembic are correctly configured.
- **Data Models:** `User`, `UserEsprit`, and `EspritData` models are refactored and stable.
- **Configuration:** The `ConfigManager` successfully loads all game-balancing values from `game_settings.json`.
- **Esprit Progression:**
    - The `/esprit upgrade` command is fully functional and correctly spends **Moonglow** based on the config formula.
    - Leveling is correctly gated by player level and Esprit rarity caps.
- **Stat & Power Calculations:** All Esprit stats and the **Sigil** rating are calculated dynamically using formulas and weights from the config file.
- **Esprit Management:** All related commands (`/details`, `/compare`, `/dissolve`, `/search`, `/collection`) have been refactored to use the config-driven calculation methods, ensuring consistent data display.
- **Team Management:** The `/esprit team` command group (`view`, `set`, `optimize`) is functional and uses the config-driven power calculations. The `TeamSlot` enum is correctly implemented.
- **Summoning System (v2):**
    - Banners correctly cost **Azurites** (standard) and **Aether** (premium).
    - The pity system uses `rarity_pity_increment` from the config.

#### ⚠️ **Requires Final Testing & Review**
- **Economic Balance:** Gameplay testing is needed to ensure the daily income of currencies feels balanced against the costs of upgrading, limit breaking, and summoning.
- **Summoning Algorithm:** The code in `summon_cog.py` needs a final review to ensure it perfectly matches the algorithm specified in Section 3 below.

---
### 3 • Key System Specifications

#### Summoning Algorithm (`/summon`)
1.  **Banner Selection:** User chooses `standard` (Azurites) or `premium` (Aether).
2.  **Cost Deduction:** Deduct `cost_single` of the appropriate currency from the `User` model.
3.  **Rarity Roll:** Roll for rarity based on the banner's configured weights.
4.  **Pity Calculation:**
    - Fetch the user's current pity score.
    - `new_pity = old_pity + rarity_pity_increment[rolled_rarity]`
5.  **Pity Guarantee Check:**
    - `IF new_pity >= pity_system_guarantee_after`:
        - If the rolled rarity was below `Epic`, force the result to be a random `Epic` Esprit.
        - Set `new_pity = 0`.
6.  **Esprit Creation:** Create the `UserEsprit` instance and save it to the database.
7.  **Result Embed:** Display the result with the pity progress bar, using the format:
    - `<emoji> **<name>**`
    - `**<rarity>** | Sigil: 💥 <power>`
    - `[█████─────] 42 %`
    - Footer: `UID`

---
### 4 • Next Development Priorities (Action Plan)

#### **HIGH PRIORITY - Gameplay & Database Integrity**
1.  **Database Migration: Remove `current_xp`**
    - **Task:** The `current_xp` column on the `user_esprits` table is now obsolete and must be removed to finalize the migration.
    - **Action:** Execute the Alembic migration process (`revision` -> `edit` -> `upgrade head`) to drop this column from the database schema.
2.  **Audit Activity Rewards:**
    - **Task:** Search all gameplay cogs (`economy_cog`, `combat_cog`, etc.) for any commands that grant rewards.
    - **Action:** **Delete all instances of Esprit XP being awarded.** Ensure that currency rewards (Nyxies, Essence) are granted correctly and, if hardcoded, refactor them to use values from the `activity_rewards` section of `game_settings.json`.

#### **MEDIUM PRIORITY - System Hardening & Cleanup**
1.  **Verify Summoning Cog:**
    - **Task:** Do a line-by-line review of `summon_cog.py`.
    - **Action:** Ensure the implementation perfectly matches the algorithm detailed in **Section 3** of this directive, especially the logic for pity calculation, cost deduction (Azurites vs. Aether), and the guarantee.
2.  **Review Admin Commands:**
    - **Task:** Update commands in `admin_cog.py` to be compatible with the new systems.
    - **Action:** For example, a command like `/admin-give-xp` should be renamed or repurposed to `/admin-give-moonglow`. Ensure all admin tools work as expected for testing and support.

#### **LOW PRIORITY - Polish & UX**
1.  **UI Consistency:**
    - **Task:** Perform a final pass on all bot embeds and messages sent by the bot.
    - **Action:** Ensure consistent terminology (e.g., "Sigil" instead of "Power"), clear formatting, and helpful error messages across the entire bot.
2.  **Documentation:**
    - **Task:** Add comments to any new or complex functions you create in other cogs.
    - **Action:** Briefly explain what each function does, what its inputs are, and what it returns. This will make future maintenance much easier.

---
### 5 • Pre-Merge & Deployment Checklist
*A final check before any new feature branch is merged.*

- [ ] **Guarantees Upheld:** The changes adhere to all principles in Section 1.
- [ ] **Linter Pass:** The code is clean and passes `ruff` / `flake8` checks.
- [ ] **Config Keys:** Any new tunable values have been added to `game_settings.json` and documented.
- [ ] **Alembic Vetted:** If the change required a database migration, the script has been manually reviewed.
- [ ] **Successful Boot:** The bot starts without errors and a clean slash-command sync.
