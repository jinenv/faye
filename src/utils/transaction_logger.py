# src/utils/transaction_logger.py
import logging
from typing import Dict
import discord

# --- 1. IMPORT THE NEW LOGGER FUNCTION ---
from src.utils.logger import get_transaction_logger
from src.database.models import User, UserEsprit, EspritData

# --- 2. GET THE DEDICATED LOGGER INSTANCE ONCE ---
tx_logger = get_transaction_logger()

def log_daily_claim(interaction: discord.Interaction, rewards: Dict[str, int]):
    """
    Logs a successful daily claim transaction.
    """
    user = interaction.user
    rewards_str = ", ".join(f"{amount:,} {currency}" for currency, amount in rewards.items() if amount > 0)
    # --- 3. USE THE DEDICATED LOGGER ---
    tx_logger.info(
        f"[DAILY_CLAIM] User: {user.id} ({user.display_name}) | Received: {rewards_str}"
    )

def log_craft_item(
    interaction: discord.Interaction,
    item_name: str,
    crafted_amount: int,
    cost_str: str,
):
    """
    Logs a successful item crafting transaction.
    """
    user = interaction.user
    # --- 3. USE THE DEDICATED LOGGER ---
    tx_logger.info(
        f"[CRAFT] User: {user.id} ({user.display_name}) | Crafted: {crafted_amount:,}x {item_name} | Cost: {cost_str}"
    )

def log_summon(
    interaction: discord.Interaction,
    banner: str,
    cost_str: str,
    esprit_data: EspritData,
    user_esprit: UserEsprit,
):
    """
    Logs a successful Esprit summoning transaction.
    """
    user = interaction.user
    tx_logger.info(
        f"[SUMMON] User: {user.id} ({user.display_name}) | Banner: {banner.upper()} | "
        f"Cost: {cost_str} | Result: '{esprit_data.name}' (Rarity: {esprit_data.rarity}, ID: {user_esprit.id})"
    )

def log_new_user_registration(
    interaction: discord.Interaction,
    new_user: User,
    starter_esprit_data: EspritData,
    starter_currencies: Dict[str, int]
):
    """
    Logs a new user registration event.
    """
    user = interaction.user
    
    # Format the starting currencies into a readable string from the config dictionary
    starter_items_str = ", ".join(
        f"{amount:,} {currency}" for currency, amount in starter_currencies.items() if amount > 0
    ) or "None"

    tx_logger.info(
        f"[NEW_USER] User: {user.id} ({user.display_name}) registered. | "
        f"Starter Esprit: '{starter_esprit_data.name}' ({starter_esprit_data.rarity}) | "
        f"Starter Items: {starter_items_str}"
    )

def log_esprit_upgrade(
    interaction: discord.Interaction,
    esprit: UserEsprit,
    old_level: int,
    cost: int,
):
    """
    Logs a successful Esprit upgrade transaction.
    """
    user = interaction.user
    ed = esprit.esprit_data
    tx_logger.info(
        f"[UPGRADE] User: {user.id} ({user.display_name}) | Esprit: '{ed.name}' ({esprit.id}) | "
        f"Level: {old_level} -> {esprit.current_level} | Cost: {cost:,} Moonglow"
    )

def log_limit_break(
    interaction: discord.Interaction,
    esprit: UserEsprit,
    costs: Dict[str, int]
):
    """
    Logs a successful Esprit limit break transaction.
    """
    user = interaction.user
    ed = esprit.esprit_data
    cost_str = ", ".join(f"{v:,} {k}" for k, v in costs.items())
    tx_logger.info(
        f"[LIMIT_BREAK] User: {user.id} ({user.display_name}) | Esprit: '{ed.name}' ({esprit.id}) | "
        f"New Breaks: {esprit.limit_breaks_performed} | Cost: {cost_str}"
    )


def log_esprit_dissolve(
    interaction: discord.Interaction,
    dissolved_esprits: list[UserEsprit],
    rewards: Dict[str, int]
):
    """
    Logs a successful Esprit dissolve transaction.
    """
    user = interaction.user
    reward_str = ", ".join(f"{v:,} {k}" for k, v in rewards.items())
    
    if len(dissolved_esprits) == 1:
        esprit = dissolved_esprits[0]
        ed = esprit.esprit_data
        tx_logger.info(
            f"[DISSOLVE] User: {user.id} ({user.display_name}) | Dissolved: '{ed.name}' ({esprit.id}) | "
            f"Received: {reward_str}"
        )
    else:
        ids = ", ".join([f"'{e.id}'" for e in dissolved_esprits])
        tx_logger.info(
            f"[BULK_DISSOLVE] User: {user.id} ({user.display_name}) | Count: {len(dissolved_esprits)} | "
            f"IDs: [{ids}] | Received: {reward_str}"
        )