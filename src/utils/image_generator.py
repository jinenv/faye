from __future__ import annotations
import os
import discord
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from functools import lru_cache
import io

from src.utils.logger import get_logger
from src.utils.config_manager import ConfigManager

logger = get_logger(__name__)

CARD_W, CARD_H = 450, 630
SPRITE_H = 550
RARITY_ICON_SIZE = (48, 48)

class ImageGenerator:
    def __init__(self, assets_base: str = "assets"):
        self.assets_base = assets_base
        fontfile = os.path.join(assets_base, "ui", "fonts", "PressStart2P.ttf")
        try:
            self.font_header = ImageFont.truetype(fontfile, 40)
        except OSError:
            logger.warning("Could not load PressStart2P font")
            self.font_header = ImageFont.load_default()

        cfg = ConfigManager()
        self.rarity_visuals = cfg.get_config("data/config/rarity_visuals") or {}

    @staticmethod
    def _hex_to_rgb(h: str):
        return tuple(int(h.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))

    @lru_cache(maxsize=32)
    def _load_rarity_icon(self, path: str) -> Image.Image | None:
        try:
            icon = Image.open(path).convert("RGBA")
            return icon.resize(RARITY_ICON_SIZE, Image.Resampling.LANCZOS)
        except FileNotFoundError:
            logger.warning(f"Rarity icon not found at path: {path}")
            return None

    def _create_rarity_aura(self, size: tuple, color: tuple) -> Image.Image:
        aura = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(aura)
        center_x, center_y = size[0] / 2, size[1] / 2
        max_radius = min(center_x, center_y) * 1.2

        for i in range(int(max_radius), 0, -5):
            alpha = int(200 * (1 - (i / max_radius))**2)
            current_color = color + (alpha,)
            draw.ellipse((center_x - i, center_y - i, center_x + i, center_y + i), fill=current_color)
            
        return aura.filter(ImageFilter.GaussianBlur(radius=70))

    def _draw_text_with_outline(self, draw, position, text, font, fill, anchor="lt"):
        x, y = position
        outline = "black"
        draw.text((x-2, y-2), text, font=font, fill=outline, anchor=anchor)
        draw.text((x+2, y-2), text, font=font, fill=outline, anchor=anchor)
        draw.text((x-2, y+2), text, font=font, fill=outline, anchor=anchor)
        draw.text((x+2, y+2), text, font=font, fill=outline, anchor=anchor)
        draw.text(position, text, font=font, fill=fill, anchor=anchor)

    def render_esprit_card(self, esprit_data: dict, **kwargs) -> Image.Image:
        card = Image.new("RGBA", (CARD_W, CARD_H), (20, 20, 20, 255))
        draw = ImageDraw.Draw(card)

        rarity_name = esprit_data.get("rarity", "Unknown")
        rarity_visual_info = self.rarity_visuals.get(rarity_name, {})
        glow_color = self._hex_to_rgb(rarity_visual_info.get("color", "#808080"))

        aura = self._create_rarity_aura((CARD_W, CARD_H), glow_color)
        card = Image.alpha_composite(card, aura)
        draw = ImageDraw.Draw(card)

        raw_path = os.path.join(self.assets_base, esprit_data.get("visual_asset_path", ""))
        sprite_img = Image.open(raw_path).convert("RGBA")
        
        w, h = sprite_img.size
        scale = SPRITE_H / h
        sprite_img = sprite_img.resize((int(w * scale), int(h * scale)), Image.Resampling.NEAREST)
        
        sprite_x = (CARD_W - sprite_img.width) // 2
        sprite_y = (CARD_H - sprite_img.height) // 2 + 30
        card.paste(sprite_img, (sprite_x, sprite_y), sprite_img)
        
        padding = 30
        
        name_text = esprit_data.get("name", "Unknown")
        self._draw_text_with_outline(draw, (CARD_W / 2, padding), name_text, self.font_header, "white", anchor="mt")

        icon_path = rarity_visual_info.get("icon_asset")
        if icon_path:
            full_icon_path = os.path.join(self.assets_base, icon_path)
            rarity_icon = self._load_rarity_icon(full_icon_path)
            if rarity_icon:
                card.paste(rarity_icon, (padding, CARD_H - RARITY_ICON_SIZE[1] - padding), rarity_icon)
        
        border_color = self._hex_to_rgb(rarity_visual_info.get("border_color", "#FFFFFF"))
        draw.rectangle([0, 0, CARD_W - 1, CARD_H - 1], outline=border_color, width=5)

        return card

    def to_discord_file(self, pil_image: Image.Image, filename: str = "image.png") -> discord.File | None:
        """
        Converts a PIL Image object into a discord.File object.

        Args:
            pil_image (Image.Image): The PIL Image to convert.
            filename (str): The desired filename for the Discord attachment.
                            Must end with a supported image extension (e.g., .png, .jpeg).

        Returns:
            discord.File: A discord.File object ready to be sent, or None if conversion fails.
        """
        try:
            image_bytes = io.BytesIO()
            if filename.lower().endswith(".png"):
                pil_image.save(image_bytes, format='PNG')
            elif filename.lower().endswith((".jpg", ".jpeg")):
                pil_image.save(image_bytes, format='JPEG')
            elif filename.lower().endswith(".gif"):
                pil_image.save(image_bytes, format='GIF')
            else:
                logger.warning(f"Unsupported image format for filename '{filename}'. Defaulting to PNG.")
                pil_image.save(image_bytes, format='PNG')
                filename = os.path.splitext(filename)[0] + ".png"

            image_bytes.seek(0)
            return discord.File(image_bytes, filename=filename)
        except Exception as e:
            logger.error(f"Failed to convert PIL Image to discord.File for '{filename}': {e}", exc_info=True)
            return None