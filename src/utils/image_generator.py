# src/utils/image_generator.py
from __future__ import annotations

import os
import textwrap
from functools import lru_cache
from typing import Tuple, Dict, Any

from PIL import (
    Image,
    ImageDraw,
    ImageFont,
    ImageFilter,
)

from src.utils.logger import get_logger
from src.utils.config_manager import ConfigManager

logger = get_logger(__name__)

# --- V4 CARD CONSTANTS (Minimalist) ---
CARD_W, CARD_H = 450, 630
SPRITE_H = 600      # Target height for the main character sprite
INFO_PANEL_H = 120  # Drastically reduced panel height

class ImageGenerator:
    """
    Generates a V4 (Minimalist) Esprit card.
    Focuses purely on art, name, and rarity for a clean summon reveal.
    """

    def __init__(self, assets_base: str = "assets"):
        self.assets_base = assets_base
        fontfile = os.path.join(assets_base, "ui", "fonts", "PressStart2P.ttf")
        try:
            self.font_lg = ImageFont.truetype(fontfile, 28)
            self.font_md = ImageFont.truetype(fontfile, 18)
        except OSError:
            logger.warning("Could not load PressStart2P – falling back to default font")
            self.font_lg = self.font_md = ImageFont.load_default()

        cfg = ConfigManager()
        self.rarity_cfg = cfg.get_config("data/config/rarity_visuals") or {}

    @staticmethod
    def _hex_to_rgb(h: str) -> Tuple[int, int, int]:
        h = h.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) if len(h) == 6 else (255, 255, 255)

    def _generate_background(self, sprite: Image.Image) -> Image.Image:
        # Create a blurred version of the sprite art as a base
        bg = sprite.resize((CARD_W, CARD_H), Image.Resampling.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(15))
        
        # Create a semi-transparent black layer to darken the background
        darken_layer = Image.new("RGBA", bg.size, (0, 0, 0, 160))
        
        # --- THIS IS THE FIX ---
        # Use alpha_composite for proper RGBA blending instead of paste
        bg = Image.alpha_composite(bg, darken_layer)
        
        return bg

    def _draw_info_panel(self, esprit_data: dict, esprit_instance) -> Image.Image:
        panel = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(panel)

        gradient = Image.new("L", (1, INFO_PANEL_H))
        for y in range(INFO_PANEL_H):
            alpha_val = min(255, int(80 + 175 * (y / INFO_PANEL_H)))
            gradient.putpixel((0, y), alpha_val)
        alpha = gradient.resize((CARD_W, INFO_PANEL_H), Image.Resampling.LANCZOS)
        
        panel_bg = Image.new("RGBA", (CARD_W, INFO_PANEL_H), (10, 10, 10, 255))
        panel_bg.putalpha(alpha)
        panel.paste(panel_bg, (0, CARD_H - INFO_PANEL_H), panel_bg)
        
        rarity = esprit_data.get("rarity", "Common")
        rarity_color = self._hex_to_rgb(self.rarity_cfg.get(rarity, {}).get("color", "#FFFFFF"))
        
        y = CARD_H - INFO_PANEL_H + 30
        x_pad = 25
        
        draw.text((x_pad, y), esprit_data.get("name", "Unknown"), font=self.font_lg, fill="white")
        y += 40
        draw.text((x_pad, y), f"Lv. {esprit_instance.current_level} {rarity}", font=self.font_md, fill=rarity_color)
        
        return panel

    def render_esprit_card(self, esprit_data: dict, esprit_instance) -> Image.Image:
        raw_path = os.path.join(self.assets_base, esprit_data.get("visual_asset_path", ""))
        sprite_img = Image.open(raw_path).convert("RGBA")

        card = self._generate_background(sprite_img)

        w, h = sprite_img.size
        scale = SPRITE_H / h
        new_w, new_h = int(w * scale), int(h * scale)
        sprite_img = sprite_img.resize((new_w, new_h), Image.Resampling.NEAREST)
        
        sprite_x = (CARD_W - new_w) // 2
        sprite_y = CARD_H - new_h
        card.paste(sprite_img, (sprite_x, sprite_y), sprite_img)

        info_panel = self._draw_info_panel(esprit_data, esprit_instance)
        # Use alpha_composite here as well for safety
        card = Image.alpha_composite(card, info_panel)

        rarity = esprit_data.get("rarity", "Common")
        border_color = self._hex_to_rgb(self.rarity_cfg.get(rarity, {}).get("border_color", "#FFFFFF"))
        draw = ImageDraw.Draw(card)
        draw.rectangle([0, 0, CARD_W - 1, CARD_H - 1], outline=border_color, width=3)

        return card

