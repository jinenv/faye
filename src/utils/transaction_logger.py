# src/utils/transaction_logger.py
import logging
import json
from datetime import datetime
from typing import Dict, List, Literal

import discord

from src.database.models import User, UserEsprit, EspritData
from src.utils.logger import get_transaction_logger

# Get the dedicated logger instance once when the module is imported
tx_logger = get_transaction_logger()

def log_new_user_registration(
    interaction: discord.Interaction,
    new_user: User,
    starter_esprit_data: EspritData,
    starter_currencies: Dict[str, int]
):
    """Logs a new user registration event as a JSON object."""
    user = interaction.user
    log_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": "new_user",
        "user_id": str(user.id),
        "username": user.display_name,
        "details": {
            "starter_esprit": {
                "name": starter_esprit_data.name,
                "rarity": starter_esprit_data.rarity,
            },
            "starter_currencies": starter_currencies,
        },
    }
    tx_logger.info(json.dumps(log_data))


def log_daily_claim(interaction: discord.Interaction, rewards: Dict[str, int]):
    """Logs a successful daily claim transaction as a JSON object."""
    user = interaction.user
    log_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": "daily_claim",
        "user_id": str(user.id),
        "username": user.display_name,
        "details": {
            "rewards": rewards,
        },
    }
    tx_logger.info(json.dumps(log_data))


def log_craft_item(
    interaction: discord.Interaction,
    item_name: str,
    crafted_amount: int,
    cost_str: str,
):
    """Logs a successful item crafting transaction as a JSON object."""
    user = interaction.user
    # Attempt to parse cost from string for better data structure
    cost_amount = int("".join(filter(str.isdigit, cost_str)))
    cost_currency = "".join(filter(str.isalpha, cost_str)).strip()

    log_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": "craft_item",
        "user_id": str(user.id),
        "username": user.display_name,
        "details": {
            "item_crafted": item_name,
            "amount_crafted": crafted_amount,
            "cost": {
                "amount": cost_amount,
                "currency": cost_currency,
            },
        },
    }
    tx_logger.info(json.dumps(log_data))


def log_summon(
    interaction: discord.Interaction,
    banner: str,
    cost_str: str,
    esprit_data: EspritData,
    user_esprit: UserEsprit,
):
    """Logs a successful Esprit summoning transaction as a JSON object."""
    user = interaction.user
    
    cost_amount_str = "".join(filter(str.isdigit, cost_str))
    cost_amount = int(cost_amount_str) if cost_amount_str else 0
    cost_currency = "".join(filter(str.isalpha, cost_str)).strip().lower() or "free"

    log_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": "summon",
        "user_id": str(user.id),
        "username": user.display_name,
        "details": {
            "banner": banner,
            "cost": {
                "amount": cost_amount,
                "currency": cost_currency,
            },
            "result": {
                "esprit_id": user_esprit.id,
                "name": esprit_data.name,
                "rarity": esprit_data.rarity,
            },
        },
    }
    tx_logger.info(json.dumps(log_data))


def log_esprit_upgrade(
    interaction: discord.Interaction,
    esprit: UserEsprit,
    old_level: int,
    cost: int,
):
    """Logs a successful Esprit upgrade transaction as a JSON object."""
    user = interaction.user
    ed = esprit.esprit_data
    log_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": "esprit_upgrade",
        "user_id": str(user.id),
        "username": user.display_name,
        "details": {
            "esprit_id": esprit.id,
            "esprit_name": ed.name,
            "rarity": ed.rarity,
            "old_level": old_level,
            "new_level": esprit.current_level,
            "cost_amount": cost,
            "cost_currency": "virelite",
        },
    }
    tx_logger.info(json.dumps(log_data))


def log_limit_break(
    interaction: discord.Interaction,
    esprit: UserEsprit,
    costs: Dict[str, int]
):
    """Logs a successful Esprit limit break transaction as a JSON object."""
    user = interaction.user
    ed = esprit.esprit_data
    log_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": "limit_break",
        "user_id": str(user.id),
        "username": user.display_name,
        "details": {
            "esprit_id": esprit.id,
            "esprit_name": ed.name,
            "rarity": ed.rarity,
            "new_break_count": esprit.limit_breaks_performed,
            "costs": costs,
        },
    }
    tx_logger.info(json.dumps(log_data))


def log_esprit_dissolve(
    interaction: discord.Interaction,
    dissolved_esprits: List[UserEsprit],
    rewards: Dict[str, int]
):
    """Logs a successful Esprit dissolve transaction as a JSON object."""
    user = interaction.user
    log_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": "esprit_dissolve",
        "user_id": str(user.id),
        "username": user.display_name,
        "details": {
            "dissolved_count": len(dissolved_esprits),
            "dissolved_esprits": [
                {"id": e.id, "name": e.esprit_data.name, "level": e.current_level, "rarity": e.esprit_data.rarity}
                for e in dissolved_esprits
            ],
            "rewards": rewards,
        },
    }
    tx_logger.info(json.dumps(log_data))

def log_admin_adjustment(
    interaction: discord.Interaction,
    target_user: discord.User,
    attribute: str,
    operation: Literal["give", "remove", "set"],
    amount: int,
    old_value: int,
    new_value: int
):
    """Logs an administrative adjustment to a user's account as a JSON object."""
    admin_user = interaction.user
    log_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": "admin_adjustment",
        "user_id": str(target_user.id), # The user being affected
        "username": target_user.display_name,
        "details": {
            "admin_user_id": str(admin_user.id),
            "admin_username": admin_user.display_name,
            "target": {
                "user_id": str(target_user.id),
                "username": target_user.display_name
            },
            "change": {
                "attribute": attribute,
                "operation": operation,
                "amount": amount,
                "old_value": old_value,
                "new_value": new_value
            }
        }
    }
    tx_logger.info(json.dumps(log_data))