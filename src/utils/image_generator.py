from __future__ import annotations

import asyncio
import io
import os
from functools import lru_cache
from typing import Tuple

import discord
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from src.utils.config_manager import ConfigManager
from src.utils.logger import get_logger

logger = get_logger(__name__)

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
CARD_W, CARD_H = 450, 630
SPRITE_H = 550
RARITY_ICON_SIZE = (48, 48)

# --------------------------------------------------------------------------- #
# Image-generation helper
# --------------------------------------------------------------------------- #
class ImageGenerator:
    """
    Thread-safe, async-friendly sprite / card generator.
    All heavy Pillow work is delegated to `asyncio.to_thread`
    so the Discord event-loop never blocks.
    """

    def __init__(self, assets_base: str = "assets") -> None:
        self.assets_base = assets_base

        # ── Fonts ─────────────────────────────────────────────────────────── #
        font_path = os.path.join(assets_base, "ui", "fonts", "PressStart2P.ttf")
        try:
            self.font_header = ImageFont.truetype(font_path, size=40)
        except OSError:
            logger.warning("PressStart2P.ttf not found – falling back to default font")
            self.font_header = ImageFont.load_default()

        # ── Rarity visuals ────────────────────────────────────────────────── #
        cfg = ConfigManager()
        visuals_config = cfg.get_config("data/config/visuals") or {}
        self.rarities_data = visuals_config.get("rarities", {})

    # --------------------------------------------------------------------- #
    # Static helpers
    # --------------------------------------------------------------------- #
    @staticmethod
    def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
        return tuple(int(hex_color.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))

    # --------------------------------------------------------------------- #
    # Cached loaders
    # --------------------------------------------------------------------- #
    @lru_cache(maxsize=32)
    def _load_rarity_icon(self, full_path: str) -> Image.Image | None:
        try:
            icon = Image.open(full_path).convert("RGBA")
            return icon.resize(RARITY_ICON_SIZE, Image.Resampling.LANCZOS)
        except FileNotFoundError:
            logger.warning(f"Rarity icon not found: {full_path}")
            return None

    # --------------------------------------------------------------------- #
    # Heavy sync helpers – run inside `asyncio.to_thread`
    # --------------------------------------------------------------------- #
    def _create_rarity_aura(self, size: tuple[int, int], color: Tuple[int, int, int]) -> Image.Image:
        aura = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(aura)
        cx, cy = size[0] / 2, size[1] / 2
        max_r = min(cx, cy) * 1.2

        for r in range(int(max_r), 0, -5):
            alpha = int(200 * (1 - r / max_r) ** 2)
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color + (alpha,))
        return aura.filter(ImageFilter.GaussianBlur(radius=70))

    def _draw_text_outline(
        self,
        img_draw: ImageDraw.ImageDraw,
        pos: Tuple[int, int],
        text: str,
        font: ImageFont.FreeTypeFont,
        fill="white",
        anchor="lt",
    ) -> None:
        x, y = pos
        for ox, oy in ((-2, -2), (2, -2), (-2, 2), (2, 2)):
            img_draw.text((x + ox, y + oy), text, font=font, fill="black", anchor=anchor)
        img_draw.text(pos, text, font=font, fill=fill, anchor=anchor)

    # --------------------------------------------------------------------- #
    # Public async API
    # --------------------------------------------------------------------- #
    async def render_esprit_card(self, esprit_data: dict) -> Image.Image:
        """Create a full esprit card image without blocking the event-loop."""
        return await asyncio.to_thread(self._render_sync, esprit_data)

    async def to_discord_file(self, img: Image.Image, filename: str = "esprit_card.png") -> discord.File | None:
        """Return a ready-to-send `discord.File`, saving in a worker thread."""
        try:
            return await asyncio.to_thread(self._save_sync, img, filename)
        except Exception as exc:
            logger.error(f"to_discord_file failed for {filename}: {exc}", exc_info=True)
            return None

    # --------------------------------------------------------------------- #
    # Internal synchronous workhorses
    # --------------------------------------------------------------------- #
    def _render_sync(self, esprit_data: dict) -> Image.Image:
        # --- base card ----------------------------------------------------- #
        card = Image.new("RGBA", (CARD_W, CARD_H), (20, 20, 20, 255))
        draw = ImageDraw.Draw(card)

        # --- rarity visuals ------------------------------------------------ #
        rarity = esprit_data.get("rarity", "Unknown")
        visual = self.rarities_data.get(rarity, {}).get("visuals", {})
        glow_rgb = self._hex_to_rgb(visual.get("color", "#808080"))

        aura = self._create_rarity_aura((CARD_W, CARD_H), glow_rgb)
        card = Image.alpha_composite(card, aura)
        draw = ImageDraw.Draw(card)  # refresh after composite

        # --- sprite -------------------------------------------------------- #
        sprite_path = os.path.join(self.assets_base, esprit_data.get("visual_asset_path", ""))
        sprite_img = Image.open(sprite_path).convert("RGBA")

        # scale sprite
        scale = SPRITE_H / sprite_img.height
        sprite_img = sprite_img.resize((int(sprite_img.width * scale), SPRITE_H), Image.Resampling.NEAREST)

        sprite_x = (CARD_W - sprite_img.width) // 2
        sprite_y = (CARD_H - sprite_img.height) // 2 + 30
        card.paste(sprite_img, (sprite_x, sprite_y), sprite_img)

        # --- name text ----------------------------------------------------- #
        self._draw_text_outline(draw, (CARD_W // 2, 30), esprit_data.get("name", "Unknown"), self.font_header, anchor="mt")

        # --- rarity icon --------------------------------------------------- #
        icon_rel = visual.get("icon_asset")
        if icon_rel:
            icon_full = os.path.join(self.assets_base, icon_rel)
            if (icon := self._load_rarity_icon(icon_full)):
                card.paste(icon, (30, CARD_H - RARITY_ICON_SIZE[1] - 30), icon)

        # --- border -------------------------------------------------------- #
        border_rgb = self._hex_to_rgb(visual.get("border_color", "#FFFFFF"))
        draw.rectangle([0, 0, CARD_W - 1, CARD_H - 1], outline=border_rgb, width=5)

        return card

    def _save_sync(self, img: Image.Image, filename: str) -> discord.File:
        buf = io.BytesIO()
        fmt = "PNG"
        ext = filename.lower().split(".")[-1]
        if ext in ("jpg", "jpeg"):
            fmt = "JPEG"
        elif ext == "gif":
            fmt = "GIF"
        img.save(buf, format=fmt)
        buf.seek(0)
        return discord.File(buf, filename=filename)
