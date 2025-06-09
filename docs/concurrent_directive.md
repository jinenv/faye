Nyxa Project Directive v2
This document is the official source of truth for the Nyxa project, integrating all confirmed decisions from our development sessions.

Part 1: Foundational Accomplishments
This section codifies the current, stable state of the project.

1.1 Core Architecture & Database
Alembic Integration: The project's database schema is now fully managed by Alembic. All future schema changes will be handled through version-controlled migrations. This milestone is complete.

Data Models: The core data models (User, UserEsprit, EspritData) have been refactored to support the new economy and team systems. This milestone is complete.

Technology Stack: The project is built on a scalable foundation of Python, discord.py, and SQLModel, adhering to principles of data-driven design and asynchronous integrity.

1.2 Implemented Gameplay & Economy
Core Commands: Foundational commands for player interaction are functional (/start, /daily, /inventory, /summon).

Currency Refactor: The in-game currency system has been fully migrated to the new structure (Nyxies, Moonglow, Azurite Shards). The old currency fields (gold, dust, fragments) have been successfully removed/renamed in the database and all cogs. This milestone is complete.

Dynamic Visuals: The bot utilizes the Pillow library to generate dynamic image cards for summoned Esprits.

Part 2: Confirmed Roadmap & Vision
This section outlines the vetted plan for the project's evolution.

2.1 Player & Esprit Progression Systems
Player Leveling: A /level command will be created within a new utility_cog to provide a detailed view of a player's XP progression.

Esprit Leveling & Gating:

A player's account level will act as a gate, determining the maximum level their Esprits can reach.

The esprit_cog will be expanded with a /esprit upgrade command to allow players to spend Moonglow to level up their Esprits.

Limit Break System:

Mechanic: Once an Esprit hits its level cap for a given tier, a "Limit Break" will be required to unlock the next tier of leveling. This will cost rare materials like Azurites or high-tier Essence.

Visual Design: This progression will be displayed on the Esprit card image.

Five stars will be rendered in the card's footer.

Each limit break increment will fill a star with a grey color.

Completing all increments for a tier will turn the stars yellow, indicating a major power milestone.

2.2 Economy & Crafting
Currency Roles: The four-currency system is confirmed:

Nyxies: The universal soft currency for shops and player-to-player trading.

Azurite Shards: The primary in-game reward from activities like /explore. These convert into Azurites.

Azurites: The sole currency for the summoning system.

Moonglow: The dedicated currency for leveling Esprits.

Essence: A tiered set of crafting materials for creating items and equipment.

Core Gameplay Loop: A /explore command will be the primary source for earning Azurite Shards and Essence.

2.3 Command & Cog Structure Expansion
New utility_cog: A new cog will be created to house informational commands.

/profile: A comprehensive summary of the player's account (level, all currencies, active team).

/level: Detailed view of player XP progression.

/botinfo: General bot statistics and links.

/stats: Global game statistics (total players, etc.).

Expanded esprit_cog: This cog will become the central hub for all Esprit management.

/esprit info <id>: Detailed view of a single owned Esprit.

/esprit equip <id>: Set an Esprit as the active one for a player's profile and combat.

/esprit upgrade <id>: Level up an Esprit using Moonglow.

/esprit dissolve <id>: Release unwanted Esprits for resources.

/esprit team: A new interface to manage the 3-Esprit combat party (1 Main, 2 Support).

/esprit compare <id1> <id2>: A side-by-side comparison of two owned Esprits.

2.4 Visual & UI Enhancements
Esprit Card Footer: The footer of the dynamically generated Esprit card image will be redesigned.

Layout: It will be divided into two sections. The left will contain the five Limit Break stars. The right will contain the Esprit's CLASS NAME and its associated emoji, separated by a vertical bar (|).

Implementation: This is confirmed to be feasible within the existing ImageGenerator utility.

2.5 Long-Term Vision (Post-MVP)
Web-Based Admin Dashboard: A future goal is to build a web interface for administrative tasks, allowing for easy management of player data, Esprit definitions, and bot configurations.

Advanced Global Economy: The ultimate endgame economic feature will be a cross-server marketplace for players to trade Esprits and items, creating a dynamic, player-driven economy.

`6-9-25`