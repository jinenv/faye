Faye - Official Architectural Directive v4.0
Document Version: 4.0 (Post-Refactor)
Status: Enforced

1. Preamble
This document is the single source of truth for the Faye bot's architecture. It has been updated to reflect the lessons learned during the initial hardening and refactoring phase. All new development, without exception, must adhere to these principles to ensure the stability, maintainability, and scalability of the application. The previous directive is now obsolete.

2. Core Architectural Principles (The "Faye Way")
These principles are non-negotiable.

G1: Cogs are Controllers, Not containers.
A cog's role is to handle the lifecycle of a Discord interaction: receive the command, perform checks (permissions, rate limits), orchestrate calls to other layers, and format a response. Cogs should contain minimal business logic.

G2: Models are the Logic Layer.
All core game logic and calculations—such as stat growth, power formulas, level cap calculations, and item costs—must be defined as methods on their corresponding data models in src/database/models.py. Cogs call these methods; they do not implement or replicate their logic.

G3: Strict UI/Logic Separation.
The User Interface (UI) layer (discord.ui.View) must be decoupled from the command logic layer (Cogs).

Trivial Views (e.g., a simple confirmation with two buttons) that are single-use may be defined within the cog that uses them for convenience.
Complex or Reusable Views (e.g., paginators, multi-step forms, menus) must be defined in their own files within the src/views/ directory. This is the new standard, as seen in the refactoring of esprit_cog.py.
G4: Centralized & Structured Configuration.
All tunable game balance values (rewards, costs, cooldowns, chances, etc.) must be defined in .json files within data/config/.

Values should be loaded by a central ConfigManager class on the bot instance.
Formulas (like upgrade costs) must be stored as structured data (e.g., a dictionary with base and multiplier keys), not as raw strings that require parsing.
G5: Atomic & Safe Database Transactions.
All database operations must be performed within an async with get_session() as session: block. Furthermore, any transaction that reads data before modifying it (e.g., checking a user's balance before deducting it) must use pessimistic locking on the initial query (with_for_update=True) to prevent race conditions.

G6: Comprehensive Transactional Logging.
All significant state-changing events (e.g., currency changes, summons, upgrades, admin adjustments) must be logged as a structured JSON object. This is achieved by calling a dedicated function from src/utils/transaction_logger.py after the database transaction has been successfully committed.

G7: Consistent Command Registration.
Application command groups must be defined as app_commands.Group class attributes inside a commands.Cog class. This is the standard pattern that ensures commands are discovered and registered correctly by discord.py. Manual registration with bot.tree.add_command() within a cog's setup or cog_load is prohibited to prevent CommandAlreadyRegistered errors.

3. System Workflow
The lifecycle of a typical command interaction is as follows:

A user executes a slash command in Discord.
The FayeBot instance routes the interaction to the appropriate Cog.
The command method in the cog performs initial checks (e.g., rate limiting).
The method opens a database session using get_session().
It fetches the required data models (e.g., User, UserEsprit) from the database, using locking where necessary.
It calls logic methods on those models (e.g., ue.calculate_power()), passing in configuration values read from self.bot.config.
It commits the transaction to save changes to the database.
It calls the appropriate function from transaction_logger.py to create an audit record.
It constructs and sends a response back to the user, using a View from the src/views/ directory if the interaction is complex.
4. Path to Production
The codebase has been significantly hardened. The next and final step to make the bot truly production-ready and horizontally scalable is to address the remaining infrastructure dependency.

High Priority - Implement Distributed State: The current RateLimiter and CacheManager are in-memory only and will not work correctly in a multi-process environment. A distributed key-value store (e.g., Redis) must be implemented to handle rate limiting, caching, and distributed locks for critical operations like summoning. This is the highest technical priority.