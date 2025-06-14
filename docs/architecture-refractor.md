# Faye - Architectural Refactor Changelog

This release focuses on major architectural improvements to enhance performance, data integrity, and stability, preparing the application for future feature development.

### Changed

* **Atomic Database Transactions**
    * Refactored all database operations within Cogs (`onboarding_cog`, `summon_cog`) to ensure each command executes as a single, atomic transaction.
    * **Logic**: All database modifications (`INSERT`, `UPDATE`) are now staged in a session and committed only once at the end of a successful operation. The `async with get_session()` context manager automatically handles rollbacks on any exception.
    * **Files Affected**: `src/cogs/onboarding_cog.py`, `src/cogs/summon_cog.py`

* **Asynchronous Image Generation**
    * Offloaded synchronous, CPU-bound image generation from the main event loop to a background thread pool using `loop.run_in_executor`.
    * This prevents the bot from hanging or becoming unresponsive while generating summon card images.
    * **Files Affected**: `src/utils/image_generator.py`, `src/cogs/summon_cog.py`

* **Singleton `ConfigManager`**
    * Refactored `ConfigManager` to be a shared, singleton-like instance.
    * The instance is created once in `NyxaBot.__init__` and accessed by all Cogs via `self.bot.config_manager`, reducing redundant file I/O and improving efficiency.
    * **Files Affected**: `src/bot.py`, all files in `src/cogs/`

### Fixed

* **`AdminCog` TypeError**
    * Resolved a `TypeError` in the `/reset_db` command caused by the `populate_static_data` function requiring the shared `ConfigManager` instance. The command now correctly passes the instance from the bot object.
    * **File Affected**: `src/cogs/admin_cog.py`

* **Interaction Timeout in `/reset_db`**
    * Implemented the `defer()` / `followup.send()` pattern for the `/reset_db` command.
    * This handles long-running operations gracefully by acknowledging the interaction within Discord's 3-second timeout, preventing response failures.
    * **File Affected**: `src/cogs/admin_cog.py`

* **Windows Console `UnicodeEncodeError`**
    * Patched the application logger to explicitly use `encoding='utf-8'` for all handlers.
    * This resolves crashes when logging non-standard characters (e.g., arrows) in Windows environments.
    * **File Affected**: `src/utils/logger.py`

`6-6-25`