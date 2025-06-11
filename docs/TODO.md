# Nyxa Project: Revised Development Roadmap

This document outlines the current development priorities for Nyxa, reflecting completed milestones and the primary directives for future work.

## ✅ Completed Milestones

This foundational work is verified, stable, and complete.

-   **[x] Architectural Foundation:**
    -   **Integrated Alembic:** Successfully set up and used for all database schema changes, ensuring safe, evolutionary updates.
    -   **Established Reliable Deployment Process:** Created `start.bat`/`start.sh` to automate migrations and prevent schema-mismatch errors in a live environment.
    -   **Resolved All Critical Bugs:** Fixed paginator crashes, command timeouts, and database errors, leading to a stable application.
-   **[x] Core Progression & Economy:**
    -   **Defined XP Curves:** Player and Esprit XP progression is defined in `data/config/game_settings.json`.
    -   **Created Progression Manager:** All level-up logic is centralized in `src/utils/progression_manager.py`.
    -   **Implemented Profile & Level Commands:** Users can view their level and XP progress via `/profile` and `/level`.
    -   **Implemented Crafting System:** The Azurite Shard -> Azurite crafting loop is fully functional with the `/craft` command.
-   **[x] Admin & Backend:**
    -   **Refactored Admin Cog:** All currency management commands (`give`/`remove`/`set`) are stable and use a central helper function, reducing code duplication and improving maintainability.

---

## 1. Immediate Priority: Complete Esprit Management

This is the next feature set to be built, completing the core user experience for managing Esprits.

-   [ ] **Implement `/esprit team` command:** Create subcommands (`view`, `set`) to allow users to manage their active and support Esprits. The database model already supports this.
-   [ ] **Implement `/esprit details` command:** Allow users to view a detailed stat card for a specific owned Esprit. This can be a simple text embed initially.

## 2. UI/UX Overhaul: Dynamic Image Generation

This is a new, high-priority directive to enhance the bot's visual identity.

-   [ ] **Create `/profile` Image Card:** Refactor the `/profile` command to generate a dynamic stat card image using Pillow, replacing the text-based embed.
-   [ ] **Create `/inventory` Image View:** (Future) Re-design the inventory as a graphical view.
-   [ ] **Create visual `/esprit details` card:** (Future) Leverage the `ImageGenerator` to show Esprit stats visually.

## 3. Next Major Feature: PvE Combat Loop

This is the primary gameplay loop to be developed after Esprit Management is complete.

-   [ ] **Create Combat Cog:** Build the `src/cogs/combat_cog.py`.
-   [ ] **Implement `/adventure` Command:** Create the primary PvE command where a user's team fights random wild Esprits.
-   [ ] **Design Turn-Based Logic:** Implement combat flow, including attack order (speed), damage calculation (`ATK - DEF`), and other stats (`crit_rate`, `dodge_chance`).
-   [ ] **Grant Rewards on Victory:** Integrate with the economy and progression systems to award XP and currency.

## 4. Long-Term Architectural & Feature Goals

These are crucial for the long-term health, security, and depth of the project.

-   **[ ] Implement Esprit Stat Growth:** Define and implement the formula for how an Esprit's stats increase upon leveling up.
-   **[ ] Implement Item & Inventory System:**
    -   Define `ItemData` and `UserItem` models in the database.
    -   Expand the `/inventory` command to show items.
    -   Add items to loot tables from `/adventure`.
-   **[ ] Automated Testing:**
    -   Setup `pytest` and `pytest-asyncio`.
    -   Write unit tests for core utilities (`RNGManager`, `ProgressionManager`).
    -   Write integration tests for cogs to ensure command stability.
-   **[ ] Security & Service Enhancements:**
    -   Implement Audit Logging for all sensitive admin actions.
    -   Implement a `/backup` command for database security.
    -   Implement rate-limiting and emergency "lockdown" controls.