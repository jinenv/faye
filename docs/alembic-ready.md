# Faye Project Directive

---

## Part 1: Accomplishments (Current State)

This section codifies the current, stable state of the Faye project following the successful integration of the database migration system.

### Core Architecture
The project is a scalable Discord RPG Bot built on Python and the `discord.py` library. It successfully follows key architectural principles including clean separation of concerns via Cogs, data-driven design using external JSON configs, and asynchronous integrity.

### Database System
A robust, persistent database has been established using SQLite, managed by the `SQLModel` ORM.
- The schema is defined with three core tables: `EspritData` (static definitions), `User` (player data), and `UserEsprit` (owned instances).
- All database schema changes and static data seeding are now managed by **Alembic**, ensuring a version-controlled, production-ready workflow. This milestone is complete.

### Implemented Gameplay Features
- **Onboarding:** A `/start` command successfully onboards new players, creating their account and granting a starting bonus.
- **Summoning System:** A `/summon` command allows users to spend currency to acquire new Esprits. The results are presented in an interactive, paginated `discord.ui.View`.
- **Economy:** Core economic commands are functional, including `/daily` for rewards and `/balance`/`/inventory` for checking assets.
- **Dynamic Visuals:** The bot uses the Pillow library to dynamically generate high-quality image cards for summoned Esprits, featuring their name, art, and rarity-based visual cues.

---

## Part 2: Envisioned Features (The Roadmap)

This section outlines the vetted, documented plan for the project's evolution, forming the basis for the next development phase.

### Player and Esprit Progression System
The immediate next step is to build a formal progression system.
- This includes defining XP curves and stat growth formulas for Esprits as they level up.
- A `/profile` command will be created for users to view their progress.

### Core PvE Combat Loop
A primary gameplay loop will be introduced through new combat commands.
- An `/explore` command will serve as the main, repeatable content, rewarding players with currency and materials.
- A structured `/tower` command will provide tiered boss progression for players to climb.
- Combat will be turn-based, featuring a 3-Esprit party system (1 Main, 2 Support) and an interactive UI for skill selection.

### Expanded Economy and Item System
The economy will be deepened to support the new combat loop.
- A new `fayrite_shards` currency will be introduced as the primary reward from combat and the main cost for summoning.
- A full item system will be implemented, requiring new `ItemData` and `UserItem` tables in the database.

### Endgame and Social Systems
Long-term engagement will be driven by competitive and social features.
- A "Sigil Power" metric will be created to calculate a player's total account strength.
- A global leaderboard will rank players by this metric, fostering competition.
- Features planned for further development include a cross-server marketplace and an adventure mode.