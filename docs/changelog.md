## [v1.1.0] - 2025-06-06

### Summary

This update focuses on a major architectural improvement: centralizing all core game economy parameters into a single configuration file. This removes hardcoded values ("magic numbers") from the codebase, improving maintainability and making game balance adjustments significantly easier.

### Changed

-   **Centralized Game Settings**: All cogs now pull economic values from `data/config/game_settings.json` using the `ConfigManager` utility.
-   **Onboarding Cog**: The `/start` command no longer uses a hardcoded value for the user's starting gold. It now uses the `starting_gold` key from the configuration file.
-   **Economy Cog**: The `/daily` command's gold reward is no longer hardcoded. It is now derived from the `daily_summon_cost` key in the configuration file.
-   **Summon Cog**: Summoning costs are no longer hardcoded. The base cost for a single summon is loaded from `summon_types.standard.cost_gold` in the configuration file, and costs for multi-pulls are calculated from this base value.

### Benefits of this Refactor

-   **Single Source of Truth**: Game balance can be adjusted by editing a single `.json` file, preventing inconsistencies across different commands.
-   **Improved Maintainability**: Reduces the need to search through the codebase to find and change economic parameters.
-   **Separation of Concerns**: The application's logic (Python code) is now fully separate from its configuration data (JSON files).