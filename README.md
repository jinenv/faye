# Project Nyxa: AI Directive & State Analysis
**Last Updated:** 2025-06-10

## I. Current Verified State

This document outlines the current stable, verified state of the Nyxa project following a comprehensive phase of feature implementation, refactoring, and bug fixing. All components listed are considered production-ready.

### A. Core Systems & Features
- **Onboarding (`/start`):** New user registration is stable. It correctly provisions a default set of currencies, including the new dual-currency system for `azurites` and `azurite_shards`, and grants a starter Esprit.
- **Economy (`/inventory`, `/daily`, `/craft`):** The economy is fully functional.
    -   `/inventory` accurately reflects all user currency balances from the database.
    -   `/daily` correctly dispenses rewards based on `game_settings.json` and enforces its cooldown.
    -   The `/craft` command is fully implemented, allowing users to convert `azurite_shards` into `azurites` with robust input handling for specific amounts and the 'all' keyword.
- **Summoning (`/summon`):** The gacha system is stable. It now correctly consumes the crafted `azurites` currency, enforcing the new crafting loop. The error messaging for insufficient currency is clear and directs the user to the `/craft` command.
- **Collection (`/esprit collection`):** The command to view owned Esprits is functional. The pagination view (`CollectionView`) has been patched to be robust, preventing crashes and correctly handling button states.
- **Utility (`/profile`, `/level`, `/botinfo`):**
    -   `/profile` has been updated to correctly display the new dual-Azurit-currency system.
    -   The placeholder `/level` command has been fully implemented, providing users with a detailed view of their XP progression.
    -   `/botinfo` correctly displays bot statistics, including a live player count queried from the database.

### B. Administrative Backend (`admin_cog.py`)
- **Full Functionality Restored:** The `admin_cog` has undergone a significant overhaul. All original commands (`list`, `reload`, `reset`, `inspect`, etc.) are present and have been verified as functional.
- **Refactored Currency Commands:** All `give`/`remove`/`set` commands have been successfully refactored to use a centralized `_adjust_user_attribute` helper function. This has eliminated significant code duplication while maintaining full functionality.
- **Bug Fixes:** All previously identified critical bugs have been resolved:
    1.  The `TypeError` from the initial factory implementation is resolved.
    2.  The "Application did not respond" error caused by the dynamic command factory has been fixed by reverting to a more reliable explicit command definition pattern.
    3.  The `UnboundLocalError` in the `/list esprits` paginator is patched.
- **Database Support:** All admin commands correctly support the new `azurites` database column.

---

## II. Architectural Guarantees

The project's architecture ensures stability, scalability, and maintainability. These are the core principles that have been verified.

- **Modularity:** Functionality is strictly segregated into Cogs. Each cog manages a distinct domain of the bot's features (e.g., `EconomyCog`, `AdminCog`), allowing for independent development and reducing complexity.
- **Data Integrity & Evolution:** The use of `SQLModel` provides a typed, Python-native interface to the database. Critically, all schema changes are managed by **Alembic**, providing a version-controlled, evolutionary path for the database. This guarantees that future updates can be deployed without data loss.
- **Configuration-Driven Design:** Core game mechanics and balance values (summon costs, daily rewards, XP curves, rarity distributions) are externalized into `.json` configuration files. This decouples game design from application logic, allowing for rapid iteration and tuning.
- **Asynchronous Integrity (Concurrent Directive):** The bot is built on an asynchronous model using `asyncio` and `discord.py`. To prevent blocking the event loop, all CPU-bound tasks, specifically the dynamic generation of images with Pillow, are offloaded to a separate thread pool executor. This ensures the bot remains responsive to Discord's API at all times.
- **Deployment Reliability:** A standardized startup procedure has been established via the `start.bat`/`start.sh` scripts. This script enforces a strict order of operations: dependency installation, database migration (`alembic upgrade head`), and then application startup. This automated process guarantees that the application code will always run against a database schema that it expects, preventing schema-mismatch errors in a live environment.

---

## III. Primary Directive: Roadmap

With the core systems verified and hardened, the project directive is now to expand game features and administrative capabilities.

### A. Immediate Priority: Complete Esprit Management
The next development cycle will focus on fully implementing the remaining commands in the `esprit_cog.py`.
- **`/esprit team`:** Implement logic to view the currently equipped active and support Esprits.
- **`/esprit set`:** Implement the logic to allow users to assign their owned Esprits to their active or support team slots. Foreign key relationships in the `User` model are already in place for this.
- **`/esprit details`:** Implement a command to view a detailed, dynamically generated stat card for a specific owned Esprit, reusing the `ImageGenerator` utility.

### B. Next Major Feature: Combat System (Combat Progression)
Following the completion of Esprit management, the primary development focus will shift to implementing the core PvE combat system. The directive is to build a turn-based system where users can pit their Esprit teams against predefined enemies or challenges. This will involve:
- Designing and implementing the turn-based battle logic.
- Creating data models for enemies and encounters.
- Calculating damage and status effects based on Esprit stats.
- Developing a UI for combat within Discord.
- Granting rewards (XP, currency, items) upon victory.

### C. Service & Security Enhancement Pipeline
In parallel with feature development, the following high-priority enhancements will be implemented to ensure the bot is secure and manageable at scale.
1.  **Audit Logging:** Implement a system to log all sensitive admin actions to a private Discord channel for review.
2.  **Database Backups:** Create a secure admin command to generate and manage timestamped backups of the live database.
3.  **Advanced Admin Tools:** Build out more powerful administrative commands, including bulk operations on roles and advanced user search/filtering.
4.  **Emergency Controls:** Implement a "lockdown" command to temporarily disable high-traffic economy commands during maintenance or unforeseen emergencies.