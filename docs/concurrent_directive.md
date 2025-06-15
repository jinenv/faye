Faye - Official Architectural Directive
Document Version: 3.0 (Post-Hardening)
Status: Production Ready

This is the single source of truth for the Faye bot's architecture. All new development must adhere to these principles to ensure the stability, maintainability, and scalability of the application.

1. Core Architectural Guarantees
These principles are non-negotiable and have been implemented across the codebase.

G1. Modularity: Features are encapsulated in Cogs (src/cogs/). Shared, self-contained tools reside in src/utils/. UI components (discord.ui.View) are defined within the cogs that use them.

G2. Single-Location Logic (The Model Layer is the Logic Layer): Core game calculations (e.g., stat growth, power calculation, upgrade costs, level caps) must be defined as methods on the database model classes in src/database/models.py. Cogs must not contain game logic; they only orchestrate calls to the models.

G3. Centralized Configuration: All tunable game balance values (e.g., rewards, costs, cooldowns, chances) must be defined in .json files within the data/config/ directory. The bot loads these into a central bot.config dictionary at startup. There must be no hardcoded "magic numbers" in the cogs.

G4. Atomic & Safe Transactions: All database operations that modify data must be performed within a single async with get_session() as session: block. Any transaction that reads a value before writing it back (e.g., deducting currency) must use with_for_update=True on the initial session.get() or select() call to lock the row and prevent race conditions.

G5. Structured Transactional Logging: All significant state-changing events (currency changes, item grants, summons, upgrades) must be logged as a JSON object to transactions.log. This is achieved by calling a dedicated function in src/utils/transaction_logger.py after the database transaction has been successfully committed.

G6. Universal Rate Limiting: All user-facing application commands must be protected by an instance of the RateLimiter utility to ensure bot stability and prevent abuse.

G7. Distributed State for Scalability: Any feature requiring a cross-user or timed "lock" that must persist across bot restarts or multiple processes (e.g., preventing a user from having two summon commands active) must use a distributed, persistent key-value store like Redis. In-memory global variables (set, dict) are strictly prohibited for managing persistent or shared state.

2. System Overview
Entrypoint (run.py, src/bot.py): The application entrypoint. The FayeBot class initializes, loads all configurations into the bot.config attribute, establishes the database connection via create_db_and_tables, and loads all cogs from the src/cogs/ directory.

Database (src/database/): The data persistence layer.

models.py: The single source of truth for the database schema (via SQLModel) and all associated game logic.
db.py: Manages the database engine (SQLAlchemy) and session creation factory.
data_loader.py: A utility for seeding the database with static data (e.g., EspritData) from .json files.
Cogs (src/cogs/): The application's controllers. They handle user interactions and orchestrate the workflow:

Receive an interaction from Discord.
Perform initial checks (e.g., rate limiting).
Open a database session.
Fetch the necessary data models from the database (using locking where appropriate).
Call logic methods on those models, passing in configuration values from bot.config.
Commit the transaction to save changes.
Log the successful transaction.
Format and send a response back to the user.
Utilities (src/utils/): Shared, reusable tools for logging, rate-limiting, image generation, and other common tasks.

3. Next Steps & Path to Production
The codebase has been refactored and hardened. The architecture is now stable and consistent. The following are the high-level priorities for moving forward.

HIGH PRIORITY - Infrastructure:

Implement Distributed Locking: Replace the temporary summon lock with a robust Redis-based implementation as mandated by G7. This is the final step to make the bot truly production-ready and scalable.
MEDIUM PRIORITY - New Features:

Combat Cog: Begin development of the core gameplay loop (/explore, /trial, combat encounters). All new features must adhere strictly to the architectural guarantees outlined above.
Economic Analysis: Use the data from transactions.log to analyze currency flow and balance the game economy by tuning the values in data/config/.
LOW PRIORITY - Maintenance:

Code Documentation: Add docstrings to public methods and classes where they are missing to improve maintainability.
Dependency Updates: Periodically review and update libraries in requirements.txt.