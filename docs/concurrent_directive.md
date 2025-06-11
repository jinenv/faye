# Nyxa Project: Unified Directive & State Architecture
**Document Version:** 2.0
**Last Updated:** 2025-06-10

This document is the official source of truth for the Nyxa project. It integrates all completed milestones, architectural guarantees, and the confirmed development roadmap. It is intended for technical and strategic guidance.

---

## 1. Foundational Accomplishments & Verified State

This section codifies the current, stable state of the project. All systems listed here are implemented, tested, and considered production-ready.

-   **[x] Core Architecture & Database:**
    -   **Technology Stack:** The project is confirmed to be built on a scalable foundation of Python, `discord.py`, and `SQLModel`.
    -   **Alembic Integration:** The project's database schema is fully managed by Alembic, ensuring all future schema changes are handled through safe, version-controlled migrations.
    -   **Data Model Refactor:** The core data models (`User`, `UserEsprit`, `EspritData`) have been successfully refactored to support the new economy and team systems.
    -   **Deployment Reliability:** A standardized startup procedure (`start.bat`/`.sh`) has been established to automate dependency checks and database migrations, guaranteeing application-database sync.

-   **[x] Implemented Gameplay & Economy:**
    -   **Core Commands:** Foundational commands for player interaction (`/start`, `/daily`, `/inventory`, `/summon`) are stable and functional.
    -   **Currency System V2:** The in-game economy has been fully migrated to the four-pillar currency system (Nyxies, Moonglow, Azurite Shards, Azurites). The legacy currency fields have been successfully removed from the database and all code.
    -   **Crafting Loop:** The `/craft` command is fully implemented, allowing users to convert Azurite Shards into Azurites, which is the sole currency for the summoning system.
    -   **Progression System:** The `ProgressionManager` utility is complete and correctly calculates XP curves as defined in `game_settings.json`. The `/profile` and `/level` commands accurately reflect this data.

-   **[x] Administrative Backend & UI:**
    -   **Admin Cog Stability:** The `admin_cog` has been stabilized, with all commands (`give`, `remove`, `set`, `list`, `reload`, etc.) fully functional after removing a fragile factory pattern in favor of explicit, reliable definitions.
    -   **Dynamic Visuals:** The bot successfully utilizes the Pillow library via the `ImageGenerator` utility to generate dynamic image cards for summoned Esprits.
    -   **Paginated Views:** The `/esprit collection` command uses a robust, paginated `discord.ui.View` for a clean user experience.

---

## 2. Architectural Guarantees

The project adheres to a set of core principles that ensure its long-term health and stability.

-   **Modularity:** Functionality is strictly segregated into Cogs, allowing for organized, independent feature development.
-   **Data Integrity:** `SQLModel` provides a typed schema, while `Alembic` guarantees safe, evolutionary database changes without data loss.
-   **Configuration-Driven Design:** Game balance and core settings are externalized to `.json` files, decoupling them from application logic for rapid tuning.
-   **Asynchronous Integrity:** All blocking, CPU-bound operations (specifically image generation) are offloaded to a thread pool executor to ensure the main bot event loop remains responsive.

---

## 3. Confirmed Roadmap & Primary Directive

This section outlines the vetted plan for the project's evolution.

### 3.1. Player & Esprit Progression Systems

-   **[ ] Esprit Leveling & Gating:**
    -   A player's account level will act as a hard gate, determining the maximum level their Esprits can reach.
    -   Implement an `/esprit upgrade` command to allow players to spend **Moonglow** to level up their Esprits up to the current cap.
    -   Implement a stat-growth formula for when Esprits level up.

-   **[ ] Limit Break System:**
    -   **Mechanic:** Once an Esprit hits its level cap, a "Limit Break" will be required to unlock the next tier of leveling. This will be a resource sink for rare materials like **Azurites** and high-tier **Essence**.
    -   **Visual Indicator:** This progression will be displayed on the Esprit card image via a five-star system in the footer. Each increment fills a star with a grey color; completing a tier turns the stars yellow.

### 3.2. Economy & Core Gameplay Loop

-   **[ ] Implement Core Gameplay Loop:** The `/explore` command will be created as the primary, repeatable activity for players to earn **Azurite Shards** and **Essence**.

### 3.3. Command & Cog Structure Expansion

-   **[ ] Complete the `esprit_cog`:** This cog will be the central hub for all Esprit management.
    -   `/esprit team`: An interface to manage the 3-Esprit combat party (1 Main, 2 Support).
    -   `/esprit info <id>`: A detailed view of a single owned Esprit.
    -   `/esprit dissolve <id>`: Release unwanted Esprits in exchange for resources.
    -   `/esprit compare <id1> <id2>`: A side-by-side comparison of two owned Esprits.

-   **[ ] Expand the `utility_cog`:**
    -   The `/profile` command will be expanded to display the active team.
    -   A global `/stats` command will be created for players to view high-level game statistics (total players, total currency in circulation, etc.).

### 3.4. Visual & UI Enhancements

-   **[ ] Redesign Esprit Card Footer:** The footer of the dynamically generated Esprit card image will be redesigned to house the new visual elements.
    -   **Layout:** The left side will contain the five **Limit Break stars**. The right side will display the **CLASS NAME** and its associated emoji, separated by a vertical bar (`|`).
-   **[ ] Convert Views