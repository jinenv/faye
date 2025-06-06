# Nyxa Bot Overview & Breakdown

A concise reference for how the Nyxa Discord bot is structured, what was changed during the “SQL Manager” refactor, and how to extend it going forward.

---

## 1. High-Level Architecture

- **Bot Core** (`src/bot.py`):  
  - Instantiates `NyxaBot`, ensures database/tables exist, seeds static data, loads cogs, and syncs slash commands.
  - Uses `discord.ext.commands.Bot` with slash‐command support (`app_commands`).

- **Database Layer** (`src/database/`):  
  - **`db.py`**:  
    - Creates or migrates SQLite tables via SQLModel/SQLAlchemy (async).  
    - Populates static `EspritData` from `data/config/esprits.json` if table is empty.  
    - Exposes `get_session()` for async sessions.  
  - **`models.py`**:  
    - Defines three core tables:  
      1. `EspritData` (master list of all Esprits & their base stats)  
      2. `User` (registered players, their gold, dust, level, XP, timestamps)  
      3. `UserEsprit` (which Esprits each user owns, current HP/level/XP)  

- **Configuration Files** (`data/config/*.json`):  
  - **`esprits.json`**: All static Esprit definitions (ID ⇒ name, rarity, stats, image path).  
  - **`game_settings.json`**: Starting values (e.g., `starting_gold`, `starting_level`).  
  - Other config files: `rarity_tiers.json`, `rarity_visuals.json`, `stat_icons.json`.

- **Cogs** (`src/cogs/`):  
  1. **`onboarding_cog.py`**  
     - `/start` workflow:  
       - Checks if user exists; if not, picks a random starter Esprit, creates `User` & `UserEsprit`, sets `active_esprit_id`, generates an image, and sends welcome + tips.  
       - Enforces “policy acceptance” via a button view before creating the user record (still included in the same cog).  
  2. **`economy_cog.py`**  
     - `/balance` (shows gold, dust, gems, etc.).  
     - `/daily` (24-hour reward, scales with level, updates `last_daily_claim`).  
     - `/inventory` (lists all `UserEsprit` rows for the user, shows names/rarities).  
     - `/leaderboard` (top users by level/gold/XP).  
     - All operations use `async with get_session()` + ORM queries/commits.  
  3. **`summon_cog.py`**  
     - `/summon [amount]` (10-pull or single summons).  
     - Fetches random Esprits based on rarity weights from config, creates new `UserEsprit` records under the user, returns an interactive “pagination” view (`SummonResultView`) that pages through each summoned Esprit’s name/rarity/description.  
  4. **`admin_cog.py`**  
     - `/reset_db` (deletes all rows from `UserEsprit`, `User`, `EspritData`; then re‐calls `populate_static_data()` to reload `EspritData`).  
     - `/reload_economy` (reloads JSON files for the old economy system—now deprecated).  
     - Used primarily for development and “clear all” operations.  
  5. **(Optional) `inventory_cog.py`**  
     - Merged into `economy_cog.py` so there is only one “EconomyCog.”  

---

## 2. What Changed During the SQL Manager Refactor

### Before (File-Based / JSON “Managers”)
- **Economy & Inventory**:  
  - Data persisted in JSON files (`economy.json`, `inventory.json`).  
  - Commands read/write directly to those JSON files, leading to inconsistency & file-lock risks.  
  - `/balance`, `/daily`, `/inventory` all used ad-hoc file I/O.

- **Onboarding**:  
  - `/start` logic existed but did not integrate with a relational database.  
  - Starter Esprits and gold were tracked only in JSON (or not persisted properly).

- **Summon**:  
  - Used JSON as well (e.g. “add summoned Esprist to `inventory.json`”).  
  - Image generation was present but linking to database was minimal.

### After (SQLModel / SQLAlchemy + AsyncSession)
1. **Single Source of Truth**  
   - **ORM models** now define every column/relationship (no JSON fallback for player data).  
   - Gold, dust, XP, level, `created_at`, `last_daily_claim`, etc. live in the `user` table.  
   - Each owned Esprit is a row in `useresprit`.

2. **Atomic, Async Transactions**  
   - Every command that reads or writes uses:  
     ```python
     async with get_session() as session:
         … ORM queries (select / add / update) …
         await session.commit()
     ```
   - If anything fails midway, the transaction rolls back.

3. **Config-Driven Seeding**  
   - At bot startup, SQLModel’s `metadata.create_all()` creates tables if needed.  
   - `populate_static_data()` reads from `data/config/esprits.json` → writes into `espritdata` once.  
   - No need to duplicate static data anywhere else.

4. **Cog Responsibilities Are Clear & Separated**  
   - **OnboardingCog**: exclusively handles user sign-up (`/start`, policy acceptance) and initial Esprit summon.  
   - **EconomyCog**: exclusively handles currency, inventory, daily rewards, and leaderboards.  
   - **SummonCog**: exclusively handles advanced summon logic (multi‐pulls, image pagination).  
   - **AdminCog**: exclusively handles dev/admin tasks (DB reset, reseeding).

---

## 3. Database Schema (Key Tables)

### 3.1 `EspritData`
| Column             | Type      | Notes                                                           |
|--------------------|-----------|-----------------------------------------------------------------|
| `esprit_id`        | `VARCHAR` | Primary key (e.g. `"ice_wyvern_juvenile"`)                      |
| `name`             | `VARCHAR` | Display name (e.g. `"Ice Wyvern Juvenile"`)                     |
| `description`      | `VARCHAR` | Lore/description                                                |
| `rarity`           | `VARCHAR` | `"Common"`, `"Rare"`, `"Epic"`, etc.                            |
| `visual_asset_path`| `VARCHAR` | Path to image asset                                             |
| `base_hp`, etc.    | `INTEGER` | All base stats (`hp`, `attack`, `defense`, `speed`, etc.)       |

### 3.2 `User`
| Column             | Type         | Notes                                                                                 |
|--------------------|--------------|---------------------------------------------------------------------------------------|
| `user_id`          | `VARCHAR`    | Primary key: Discord user ID (string).                                                |
| `username`         | `VARCHAR`    | Stored Discord username (not necessarily unique if a user changes their tag).         |
| `level`, `xp`      | `INTEGER`    | Level & experience points.                                                            |
| `gold`, `dust`     | `INTEGER`    | Main & secondary currencies.                                                          |
| `last_daily_claim` | `DATETIME`   | Timestamp of last `/daily` usage (UTC ISO format).                                    |
| `active_esprit_id` | `VARCHAR`    | FK → `useresprit.id`; which `UserEsprit` is currently “active.”                       |
| `created_at`       | `DATETIME`   | Defaults to `CURRENT_TIMESTAMP`.                                                      |

### 3.3 `UserEsprit`
| Column             | Type      | Notes                                                                                           |
|--------------------|-----------|-------------------------------------------------------------------------------------------------|
| `id`               | `VARCHAR` | Primary key (UUID).                                                                             |
| `owner_id`         | `VARCHAR` | FK → `user.user_id`; the user who owns this Esprit.                                             |
| `esprit_data_id`   | `VARCHAR` | FK → `espritdata.esprit_id`; which static Esprit definition it corresponds to.                  |
| `current_hp`       | `INTEGER` | Current HP (starts at `base_hp` from `EspritData`).                                             |
| `current_level`    | `INTEGER` | Evolve/level‐up tracking (starts at `1` for a brand‐new summon).                                |
| `current_xp`       | `INTEGER` | XP toward next level for that Esprit.                                                           |

---

## 4. Core Bot File: `src/bot.py` (After Refactor)

```python
import os
import asyncio
import discord
from discord.ext import commands

from src.database.db import create_db_and_tables, populate_static_data
from src.utils.logger import get_logger

logger = get_logger(__name__)

class NyxaBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # 1. Ensure DB & tables exist, seed static EspritData
        await create_db_and_tables()
        await populate_static_data()
        logger.info("Database tables ready & EspritData seeded.")

        # 2. Load cogs (in logical order)
        await self.load_extension("src.cogs.onboarding_cog")
        await self.load_extension("src.cogs.economy_cog")
        await self.load_extension("src.cogs.summon_cog")
        await self.load_extension("src.cogs.admin_cog")
        logger.info("All cogs loaded.")

        # 3. Sync slash commands
        await self.tree.sync()
        logger.info("Slash commands synced.")

    async def on_ready(self):
        logger.info(f"NyxaBot is online as {self.user} (ID: {self.user.id}).")

async def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        logger.critical("DISCORD_TOKEN not found.")
        return
    bot = NyxaBot()
    try:
        await bot.start(token)
    except KeyboardInterrupt:
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())
