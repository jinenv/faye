# src/utils/image_generator.py
from __future__ import annotations

import os
import colorsys
from collections import Counter
from functools import lru_cache
from typing import Tuple, Dict, Any

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

from src.utils.logger import get_logger
from src.utils.config_manager import ConfigManager

logger = get_logger(__name__)

# ──────────────────────────────────────────────
# constants & tunables
# ──────────────────────────────────────────────
BRIGHT_MIN = 40          # dominant-colour threshold
SAT_MIN    = 0.15
BLEND_WITH_RARITY = False    # if True -> dominant colour & rarity colour averaged

PAD        = 40          # canvas padding
SPRITE_H   = 512         # sprite height  (will be square)
ICON_SIZE  = (32, 32)    # icon tiles
ROW_H      = 64          # stat-row height
CANVAS_W   = 800         # fixed width

# ──────────────────────────────────────────────
class ImageGenerator:
    """Renders a single ‘detail card’ for an Esprit instance."""

    def __init__(self, assets_base: str = "assets") -> None:
        self.assets_base = assets_base

        # fonts ───────────────────────────────
        fontfile = os.path.join(assets_base, "ui", "fonts", "PressStart2P.ttf")
        try:
            self.font_lg  = ImageFont.truetype(fontfile, 72)
            self.font_md  = ImageFont.truetype(fontfile, 54)
        except OSError:
            logger.warning("Could not load PressStart2P – using default font")
            self.font_lg = self.font_md = ImageFont.load_default()

        # config files ────────────────────────
        cfg = ConfigManager()
        self.rarity_cfg: Dict[str, Any] = cfg.get_config("data/config/rarity_visuals") or {}
        self.icon_cfg:   Dict[str, Any] = cfg.get_config("data/config/stat_icons")     or {}

        # sprite-sheet held open once & cached
        sheet_path = os.path.join(self.assets_base, self.icon_cfg.get("sprite_sheet", ""))
        if os.path.isfile(sheet_path):
            self.sheet = Image.open(sheet_path).convert("RGBA")
        else:
            logger.error("Icon sprite-sheet not found: %s", sheet_path)
            self.sheet = None

        self.tile = self.icon_cfg.get("tile_size", 32)

    # ────────────────── helpers
    @staticmethod
    def _hex(hexstr: str) -> Tuple[int, int, int]:
        h = hexstr.lstrip("#")
        if len(h) != 6:
            return (255, 255, 255)
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))

    @lru_cache(maxsize=256)
    def _slice_icon(self, col: int, row: int) -> Image.Image:
        """Extract a tile from the sprite-sheet → resized to ICON_SIZE."""
        if not self.sheet:
            return Image.new("RGBA", ICON_SIZE, (0, 0, 0, 0))

        box = (col * self.tile,
               row * self.tile,
               col * self.tile + self.tile,
               row * self.tile + self.tile)

        icon = self.sheet.crop(box).resize(ICON_SIZE, Image.Resampling.NEAREST)
        return icon

    def _icon_coords(self, key: str):
        """Look up (col,row) in stat_icons.json – tolerant to spaces / case."""
        icons = self.icon_cfg.get("icons", {})
        key1  = key.lower().replace(" ", "")   # hp   / mpreg etc.
        key2  = key.lower()                    # "mp reg"
        return icons.get(key1) or icons.get(key2)

    # dominant-colour utilities ───────────────
    @staticmethod
    def _dominant(img: Image.Image) -> Tuple[int, int, int]:
        pixels = [px for px in img.getdata() if px[3] > 0]
        if not pixels:
            return (255, 255, 255)
        r, g, b, _ = Counter(pixels).most_common(1)[0][0]
        return (r, g, b)

    @staticmethod
    def _usable(rgb: Tuple[int, int, int]) -> bool:
        r, g, b = rgb
        bright = (r + g + b) / 3
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        return bright >= BRIGHT_MIN and s >= SAT_MIN

    @staticmethod
    def _blend(a: Tuple[int, int, int],
               b: Tuple[int, int, int],
               t: float = 0.5) -> Tuple[int, int, int]:
        return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))

    # add glow behind sprite ──────────────────
    def _sprite_glow(self, sprite: Image.Image,
                     rarity_rgb: Tuple[int, int, int]) -> Image.Image:
        dom = self._dominant(sprite)
        glow_rgb = dom if self._usable(dom) else rarity_rgb
        if BLEND_WITH_RARITY and self._usable(dom):
            glow_rgb = self._blend(dom, rarity_rgb, 0.5)

        glow = Image.new("RGBA", sprite.size, (*glow_rgb, 255))
        glow.putalpha(sprite.split()[-1])
        glow = glow.filter(ImageFilter.GaussianBlur(18))

        out = Image.new("RGBA", sprite.size, (0, 0, 0, 0))
        out.paste(glow, (0, 0), glow)
        out.paste(sprite, (0, 0), sprite)
        return out

    # ────────────────── public API
    async def render_esprit_detail_image(
        self,
        esprit_data: dict | None = None,
        esprit_instance=None,
        include_description: bool = False,
        # legacy-alias keeps old cogs happy ↓↓↓
        esprit_data_dict: dict | None = None,
) -> Image.Image:
        # accept either name
        if esprit_data is None:
            esprit_data = esprit_data_dict or {}

        # sprite (scaled) + glow ───────────────────────────
        vis_path = os.path.join(self.assets_base,
                                esprit_data.get("visual_asset_path", ""))
        sprite = Image.open(vis_path).convert("RGBA").resize(
            (SPRITE_H, SPRITE_H), Image.Resampling.NEAREST)

        rarity = esprit_data.get("rarity", "Common")
        rarity_rgb = self._hex(self.rarity_cfg.get(rarity, {}).get("color", "#FFFFFF"))
        sprite = self._sprite_glow(sprite, rarity_rgb)

        # canvas size (5 stat rows) ────────────────────────
        H = (PAD + SPRITE_H + 30 + self.font_lg.size + 20 +
             self.font_md.size * 2 + 40 + ROW_H * 5 + PAD)
        base = Image.new("RGBA", (CANVAS_W, int(H)), (30, 30, 30, 255))
        draw = ImageDraw.Draw(base)

        # border
        border_rgba = (*self._hex(self.rarity_cfg.get(rarity, {})
                                  .get("border_color", "#A9A9A9")), 255)
        draw.rectangle([0, 0, CANVAS_W - 1, int(H) - 1],
                       outline=border_rgba, width=8)

        # vignette
        vign = Image.new("L", base.size, 0)
        ImageDraw.Draw(vign).ellipse(
            (-CANVAS_W * 0.2, -H * 0.1, CANVAS_W * 1.2, H * 1.5), fill=255)
        vign = vign.filter(ImageFilter.GaussianBlur(250))
        base = Image.composite(base,
                               Image.new("RGBA", base.size, (10, 10, 10, 255)),
                               vign)
        draw = ImageDraw.Draw(base)

        # sprite paste
        base.paste(sprite, ((CANVAS_W - SPRITE_H) // 2, PAD), sprite)

        # headings ─────────────────────────────────────────
        y = PAD + SPRITE_H + 30
        cx = CANVAS_W // 2

        draw.text((cx, y), esprit_data.get("name", "Unknown"),
                  font=self.font_lg,  fill="white", anchor="mt")
        y += self.font_lg.size + 20

        draw.text((cx, y), f"Rarity: {rarity}",
                  font=self.font_md, fill=rarity_rgb, anchor="mt")
        y += self.font_md.size + 20

        draw.text((cx, y), f"Level: {esprit_instance.current_level}",
                  font=self.font_md, fill=(200, 200, 255, 255), anchor="mt")
        y += self.font_md.size + 20

        # stats (left & right lists stay exactly as before) ───────────────
        left = [("HP", esprit_instance.current_hp),
                ("ATK", esprit_data["base_attack"]),
                ("DEF", esprit_data["base_defense"]),
                ("SPD", esprit_data["base_speed"]),
                ("MP",  esprit_data.get("base_mana", 0))]

        right = [("MR",    esprit_data.get("base_magic_resist", 0)),
                 ("CRIT",  f"{esprit_data.get('base_crit_rate',0)*100:.1f}%"),
                 ("BLOCK", f"{esprit_data.get('base_block_rate',0)*100:.1f}%"),
                 ("DODGE", f"{esprit_data.get('base_dodge_chance',0)*100:.1f}%"),
                 ("MP REG", esprit_data.get("base_mana_regen", 0))]

        bar_x = CANVAS_W // 2

        for i, ((lk, lv), (rk, rv)) in enumerate(zip(left, right)):
            row_y  = y + i * ROW_H
            text_y = int(row_y + (ROW_H - self.font_md.size) // 2)

            # left cell ---------------------------------------------------
            coords = self._icon_coords(lk)
            if coords:
                icon = self._slice_icon(*coords)
                base.paste(icon,
                           (bar_x - 40 - ICON_SIZE[0],
                            row_y + (ROW_H - ICON_SIZE[1]) // 2),
                           icon)

            draw.text((bar_x - 40 - ICON_SIZE[0] - 10, text_y),
                      str(lv), font=self.font_md,
                      fill="white", anchor="rm")

            # divider
            draw.text((bar_x, text_y), "|",
                      font=self.font_md,
                      fill=(180, 180, 180, 255), anchor="mm")

            # right cell --------------------------------------------------
            coords = self._icon_coords(rk)
            if coords:
                icon = self._slice_icon(*coords)
                base.paste(icon,
                           (bar_x + 40,
                            row_y + (ROW_H - ICON_SIZE[1]) // 2),
                           icon)

            draw.text((bar_x + 40 + ICON_SIZE[0] + 10, text_y),
                      str(rv), font=self.font_md,
                      fill="white", anchor="lm")

        return base

