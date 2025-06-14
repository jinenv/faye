# Faye Bot Overview & Breakdown

A concise reference for how the Faye Discord bot is structured, what was changed during the “SQL Manager” refactor, and how to extend it going forward.

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
      2. `User` (registered players, their faylen, virelite, level, XP, timestamps)  
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
     - `/balance` (shows faylen, virelite, gems, etc.).  
     - `/daily` (24-hour reward, scales with level, updates `last_daily_claim`).  
     - `/inventory` (lists all `UserEsprit` rows for the user, shows names/rarities).  
     - `/leaderboard` (top users by level/faylen/XP).  
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
  - Starter Esprits and faylen were tracked only in JSON (or not persisted properly).

- **Summon**:  
  - Used JSON as well (e.g. “add summoned Esprist to `inventory.json`”).  
  - Image generation was present but linking to database was minimal.

### After (SQLModel / SQLAlchemy + AsyncSession)
1. **Single Source of Truth**  
   - **ORM models** now define every column/relationship (no JSON fallback for player data).  
   - Faylen, virelite, XP, level, `created_at`, `last_daily_claim`, etc. live in the `user` table.  
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
| `rarity`           | `VARCHAR` | `"Common"`, `"Rare"`, `"Epic"`, etc.                             |
| `visual_asset_path`| `VARCHAR` | Path to image asset                                              |
| `base_hp`, etc.    | `INTEGER` | All base stats (`hp`, `attack`, `defense`, `speed`, etc.)       |

### 3.2 `User`
| Column             | Type         | Notes                                                                                  |
|--------------------|--------------|----------------------------------------------------------------------------------------|
| `user_id`          | `VARCHAR`    | Primary key: Discord user ID (string).                                                |
| `username`         | `VARCHAR`    | Stored Discord username (not necessarily unique if a user changes their tag).         |
| `level`, `xp`      | `INTEGER`    | Level & experience points.                                                             |
| `faylen`, `virelite`     | `INTEGER`    | Main & secondary currencies.                                                           |
| `last_daily_claim` | `DATETIME`   | Timestamp of last `/daily` usage (UTC ISO format).                                     |
| `active_esprit_id` | `VARCHAR`    | FK → `useresprit.id`; which `UserEsprit` is currently “active.”                         |
| `created_at`       | `DATETIME`   | Defaults to `CURRENT_TIMESTAMP`.                                                       |

### 3.3 `UserEsprit`
| Column             | Type      | Notes                                                                                           |
|--------------------|-----------|-------------------------------------------------------------------------------------------------|
| `id`               | `VARCHAR` | Primary key (UUID).                                                                             |
| `owner_id`         | `VARCHAR` | FK → `user.user_id`; the user who owns this Esprit.                                            |
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
```

## 5. How to Extend / Add New Features

### 5.1 Adding a New Currency (e.g., “Gems”)
Update User model in src/database/models.py

`src/database/models.py`

```python
from datetime import datetime
from sqlmodel import Field, SQLModel
from typing import Optional

class User(SQLModel, table=True):
    user_id: str = Field(primary_key=True)
    username: str
    level: int = Field(default=1)
    xp: int = Field(default=0)
    faylen: int = Field(default=0)
    virelite: int = Field(default=0)

    # ← New column
    gems: int = Field(default=0, nullable=False)

    last_daily_claim: Optional[datetime] = None
    active_esprit_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
```


Recreate the database (if in dev):

Delete faye.db and restart bot → tables are rebuilt.

Existing players will lose data; for a production environment, use an Alembic migration instead:

> ALTER TABLE "user" ADD COLUMN gems INTEGER NOT NULL DEFAULT 0;

`Update config (optional) in game_settings.json:`

```jsonc
{
  "starting_gold": 500,
  "starting_level": 1,
  "starting_gems": 10
}
```

`Modify OnboardingCog to give new users 10 gems:`

```python
new_user = User(
    user_id=str(interaction.user.id),
    username=interaction.user.name,
    level=self.game_settings["starting_level"],
    xp=0,
    faylen=self.game_settings["starting_gold"],
    virelite=0,
    gems=self.game_settings.get("starting_gems", 0),
    active_esprit_id=None
)
Expose in EconomyCog (balance, daily, etc.):
```

```python
# In /balance:
embed = discord.Embed(
    title="💰 Wallet",
    description=(
        f"Faylen: **{user.faylen:,}**\n"
        f"Virelite: **{user.virelite:,}**\n"
        f"Gems: **{user.gems:,}**"
    )
)

# In /daily (if you want to grant 1 gem/day):
user.gems += 1
session.add(user)
await session.commit()
```
### 5.2 Adding a New Table / Feature (e.g., “AuctionHouse”)

`New ORM model in src/database/models.py:` 

```python
from uuid import uuid4
from datetime import datetime

class AuctionListing(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    seller_id: str = Field(foreign_key="user.user_id")
    esprit_id: str = Field(foreign_key="useresprit.id")
    price_gold: int
    created_at: datetime = Field(default_factory=datetime.utcnow)

```
> Restart / migrate so that SQLModel creates the auctionlisting table.

`New Cog (src/cogs/auction_cog.py):`

```python

import discord
from discord.ext import commands
from discord import app_commands
from sqlalchemy.future import select
from src.database.db import get_session
from src.database.models import AuctionListing, UserEsprit

class AuctionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="list", description="List your Esprit for sale")
    @app_commands.describe(esprit="Which Esprit to sell", price="Price in faylen")
    async def list(self, interaction: discord.Interaction, esprit: str, price: int):
        user_id = str(interaction.user.id)
        async with get_session() as session:
            # Verify the user owns that Esprit
            stmt = select(UserEsprit).where(
                UserEsprit.id == esprit,
                UserEsprit.owner_id == user_id
            )
            owned = (await session.execute(stmt)).scalar_one_or_none()
            if not owned:
                await interaction.response.send_message(
                    "You don’t own that Esprit!", ephemeral=True
                )
                return

            # Create an AuctionListing
            new_listing = AuctionListing(
                seller_id=user_id,
                esprit_id=esprit,
                price_gold=price
            )
            session.add(new_listing)
            await session.commit()

        await interaction.response.send_message(
            f"Your Esprit has been listed for **{price:,} faylen**!"
        )

async def setup(bot):
    await bot.add_cog(AuctionCog(bot))
```
Load it in bot.py:

```python
await self.load_extension("src.cogs.auction_cog")
```

Use `/auctions` or `/buy` commands later to query AuctionListing table` with ORM.

## 6. Why This Approach “Prepares” Us for Future Plans

Schema‐First, Single Source of Truth

All tables and columns are defined once in models.py. No scattered JSON or ad-hoc SQLite calls.

Changing a column (e.g., renaming, adding) happens in one place. Migrations or a fresh DB recreate it correctly.

Async ORM with Transactions

get_session() + session.commit() ensures consistency: either everything in a command completes or nothing does (rollbacks on error).

No risk of partial writes or JSON file corruption.

Config‐Driven Defaults

data/config/*.json files centralize starting values, rarity weights, visuals, etc.

To tweak rates or default currencies, edit JSON—no code change required.

Modular Cog Structure

Each “feature set” (onboarding, economy, summons, admin) lives in its own Cog file.

Adding new features (quests, PvP, auctions, guilds) simply requires a new Cog, which shares the same get_session()/ORM models.

Commands are cleanly namespaced (no collisions), and slash commands sync automatically.

Ease of Extension

Adding a new currency, stat, or table is a 3-step process: update model → (re)create DB or run a migration → update relevant cogs.

Adding new commands or UIs: create a new Cog, use the same async-ORM pattern. No rewriting existing logic.

Consistency & Maintainability

Everyone reads/writes from the same database, same tables, same config. Maintenance becomes a matter of editing ORM models or JSON, rather than tracking down file I/O code.

New devs immediately see “models.py” as the full data schema, “db.py” as the database setup/seed step, and “cogs/” as separated feature modules.

## 7. Summary of “Before” vs. “After”
 
| Aspect                    | Before Refactor                            | After Refactor (SQL Manager)                                        |
|---------------------------|--------------------------------------------|---------------------------------------------------------------------|
| Persistence               | JSON files + ad-hoc SQLite calls           | Async SQLModel/SQLAlchemy (single SQLite file)                      |
| User Data                 | Tracked in economy.json / inventory.json   | Tracked in User & UserEsprit tables (ORM models)                    |
| Static Data (Esprits)     | JSON loaded on each summon or ad-hoc load  | Seeded once at startup via populate_static_data()                   |
| Command Logic             | Mixed file I/O and raw SQL/JSON parsing    | All commands use `async with get_session()` + ORM                   |
| Onboarding (`/start`)     | Partial, not linked to database schema     | Full—creates user row, starter Esprit, initial faylen, commits to DB  |
| Economy (`/balance`, etc) | File-based, risk of out-of-sync data       | DB-based, consistent, atomic updates                                |
| Summons                   | JSON/in-memory; inconsistent pagination    | DB-based; interactive multi-pull pagination view                    |
| Admin Tools               | Manual JSON deletes / raw SQL              | `/reset_db` resets ORM tables and reseeds EspritData                |
| Extensibility             | Harder—scattered JSON, inconsistent API    | Easy—add columns to models, new cogs, simple migration              |


## 8. Folder & File Structure (After Refactor)

faye/
├─ data/
│   └─ config/
│       ├─ esprits.json
│       ├─ game_settings.json
│       ├─ rarity_tiers.json
│       ├─ rarity_visuals.json
│       └─ stat_icons.json
├─ src/
│   ├─ bot.py
│   ├─ database/
│   │   ├─ db.py
│   │   └─ models.py
│   ├─ cogs/
│   │   ├─ onboarding_cog.py
│   │   ├─ economy_cog.py
│   │   ├─ summon_cog.py
│   │   ├─ admin_cog.py
│   │   └─ auction_cog.py           ← Newly added for AuctionHouse
│   ├─ utils/
│   │   ├─ logger.py
│   │   ├─ config_manager.py
│   │   ├─ image_generator.py
│   │   └─ render_helpers.py
│   └─ views/
│       └─ summon_result.py
├─ faye.db  ← SQLite file (auto-created)
├─ run.py
├─ .env
└─ requirements.txt

## 9. Key Takeaways

### Maintain a single ORM schema in models.py rather than scattering JSON/file-based persistence.

### Use async SQLModel/SQLAlchemy for all DB operations; wrapping everything in get_session() ensures consistency.

### Keep configuration in JSON under data/config. Any default values or rarity weights live there.

### Separate features into Cogs: onboarding, economy, summons, admin. Each Cog reads/writes via ORM.

### Extending the system is as simple as adding a field to a model, running a migration (or deleting and recreating faye.db in dev), and adjusting relevant cogs to reference that new field.

### By following this pattern, any future feature—new currencies, new tables, new commands—will slot in without rewriting existing code or risking data inconsistency. This “SQL Manager” design lays a stable foundation for all upcoming Faye expansions.

`6-5-2025`