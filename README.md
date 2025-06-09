# Nyxa Discord RPG Bot

Nyxa is a feature-rich, scalable RPG bot for Discord, built with Python. It features a robust economy, a gacha-style summoning system for collectible creatures called Esprits, and dynamic image generation for a rich user experience.

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![discord.py](https://img.shields.io/badge/discord.py-2.3.2-7289DA.svg)
![SQLModel](https://img.shields.io/badge/SQLModel-0.0.18-brightgreen.svg)
![Pillow](https://img.shields.io/badge/Pillow-10.3.0-blueviolet.svg)

---

## Table of Contents

-   [Features](#features)
-   [Architecture](#architecture)
-   [Database Schema](#database-schema)
-   [Getting Started](#getting-started)
-   [Configuration](#configuration)
-   [Project Structure](#project-structure)

## Features

The bot currently supports the following commands and features:

-   **`/start`**: Onboards new users by creating an account, granting a configurable amount of starting nyxies, and giving them a free Epic-tier Esprit.
-   **`/summon <amount>`**: Allows users to spend nyxies to summon 1, 3, or 10 new Esprits. Results are delivered in an interactive, paginated embed that showcases each Esprit with a dynamically generated image card.
-   **`/balance`**: Lets users check their current nyxies and moonglow balances.
-   **`/daily`**: Provides a daily claim for a set amount of nyxies, with a 24-hour cooldown.
-   **`/inventory`**: Displays a list of all Esprits the user currently owns.
-   **Dynamic Image Generation**: Creates detailed, high-quality "stat cards" for summoned Esprits using the Pillow library.
-   **Administrative Tools**: Includes an admin-only `/reset_db` command for wiping and re-seeding the database during development.

## Architecture

The bot is designed with scalability and maintainability as top priorities, following a clean, modular architecture.

-   **Bot Core**: Built on `discord.py`, functionality is separated into Cogs (`src/cogs/`) for each major feature set (e.g., Onboarding, Economy, Summoning).
-   **Database**: Uses `SQLModel` as an asynchronous ORM over a SQLite database (`nyxa.db`). This provides a single source of truth for all dynamic user and game data, ensuring consistency and eliminating the risks of file-based storage. All database operations are handled through async sessions.
-   **Configuration**: All static game data—such as Esprit definitions, rarity weights, economic parameters, and visual styles—is externalized into JSON files located in `data/config/`. This allows for easy game balancing and tweaking without touching the core Python code.
-   **Utilities**: Helper modules for common tasks like logging, image generation, and error handling are organized in `src/utils/`.

## Database Schema

The database is composed of three primary tables that model the game's state.

### `EspritData`

Stores the static, base definitions for every Esprit in the game. This table is seeded from `data/config/esprits.json` at startup.

| Column              | Type      | Notes                                  |
| ------------------- | --------- | -------------------------------------- |
| `esprit_id`         | `VARCHAR` | Primary Key (e.g., "fire_golem")       |
| `name`              | `VARCHAR` | Display Name (e.g., "Fire Golem")      |
| `rarity`            | `VARCHAR` | "Common", "Epic", etc.                 |
| `visual_asset_path` | `VARCHAR` | Path to the Esprit's image.            |
| `base_hp`, etc.     | `INTEGER` | All base stats for the Esprit.         |

### `User`

Stores information for each registered player.

| Column             | Type       | Notes                                  |
| ------------------ | ---------- | -------------------------------------- |
| `user_id`          | `VARCHAR`  | Primary Key (Discord User ID).         |
| `username`         | `VARCHAR`  | User's Discord name.                   |
| `level`, `xp`      | `INTEGER`  | Player's level and experience.         |
| `nyxies`, `moonglow`     | `INTEGER`  | Player's currency balances.            |
| `last_daily_claim` | `DATETIME` | Timestamp of the last `/daily` claim.  |
| `active_esprit_id` | `VARCHAR`  | Foreign Key to the active `UserEsprit`.|

### `UserEsprit`

Represents a specific instance of an Esprit owned by a user, tracking its dynamic state.

| Column           | Type      | Notes                                  |
| ---------------- | --------- | -------------------------------------- |
| `id`             | `VARCHAR` | Primary Key (UUID).                      |
| `owner_id`       | `VARCHAR` | Foreign Key to `User.user_id`.           |
| `esprit_data_id` | `VARCHAR` | Foreign Key to `EspritData.esprit_id`.   |
| `current_hp`     | `INTEGER` | The Esprit's current health.             |
| `current_level`  | `INTEGER` | The Esprit's current level.              |
| `current_xp`     | `INTEGER` | The Esprit's current experience points.  |

## Getting Started

Follow these steps to set up and run the bot locally.

1.  **Clone the Repository**
    ```sh
    git clone <your-repository-url>
    cd nyxa
    ```

2.  **Create a Virtual Environment**
    ```sh
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

3.  **Install Dependencies**
    All required packages are listed in `requirements.txt`.
    ```sh
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables**
    Create a `.env` file in the root directory and add your Discord bot token.
    ```
    # .env
    DISCORD_TOKEN="your_bot_token_here"
    ```

5.  **Run the Bot**
    The bot can be started using `run.py`.
    ```sh
    python run.py
    ```
    On the first run, the `nyxa.db` SQLite database file will be created automatically.

## Configuration

Game balance and settings can be modified by editing the JSON files in the `data/config/` directory.

-   `esprits.json`: Contains the master list of all Esprits and their base stats.
-   `game_settings.json`: Controls core economic parameters like starting nyxies and summon costs.
-   `rarity_tiers.json`: Defines the different rarity levels and their summon probabilities.
-   `rarity_visuals.json`: Specifies the colors and other visual elements associated with each rarity tier.
-   `stat_icons.json`: Maps stat names to their corresponding icon coordinates in the stat icon sprite sheet.

## Project Structure

nyxa/
├── data/
│   └── config/         # All game balance and settings JSON files
├── docs/               # Project documentation (Changelog, To-Do, etc.)
├── assets/             # Static assets like images and fonts
├── src/
│   ├── cogs/           # Discord command modules (features)
│   ├── database/       # Database models and session management
│   ├── utils/          # Helper modules (Config, Logging, etc.)
│   └── views/          # discord.ui.View classes for interactive components
├── tools/              # Standalone developer scripts
├── .env                # (Local) Environment variables
├── run.py              # Main entry point to run the bot
├── requirements.txt    # Python package dependencies
└── nyxa.db             # (Local) SQLite database file