# src/views/summon_result.py
import discord
from typing import Optional

from src.database.models import UserEsprit
from src.utils.logger import get_logger

logger = get_logger(__name__)

class SummonResultView(discord.ui.View):
    """
    A view that is displayed after a user summons a single Esprit.
    This version contains no interactive components.
    """
    def __init__(self, esprit: UserEsprit, bot: discord.Client):
        super().__init__(timeout=180) # Timeout can be shorter now
        self.esprit = esprit
        self.bot = bot

    # The @discord.ui.button and the view_details method have been removed.