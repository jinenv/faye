# src/utils/image_generator.py
from __future__ import annotations


import os
import colorsys
from collections import Counter
from functools import lru_cache
from typing import Tuple, Dict, Any


from PIL import (
    Image,
    ImageDraw,
    ImageFont,
    ImageFilter,
    ImageOps,
)


from src.utils.logger import get_logger
from src.utils.config_manager import ConfigManager


logger = get_logger(__name__)


# ───────────────────────── constants ─────────────────────────
BRIGHT_MIN        = 40
SAT_MIN           = 0.15
BLEND_WITH_RARITY = False


PAD        = 40                  # outer padding
SPRITE_H   = 512                 # sprite square
ICON_SIZE  = (32, 32)
ROW_H      = 64                  # stat-row height
CANVAS_W   = 800


COL_GAP_L  = 180                  # left column centre → icon edge
COL_GAP_R  = 70                  # right column (pulled in)
TEXT_PAD   = 12                  # icon ↔ value text
DIVIDER_OPACITY = 38             # 0-255 ≈15 % opacity
# ─────────────────────────────────────────────────────────────




class ImageGenerator:
    """Render a detailed Esprit card."""


    # ───────────────────────── constructor ─────────────────────────
    def __init__(self, assets_base: str = "assets") -> None:
        self.assets_base = assets_base


        fontfile = os.path.join(assets_base, "ui", "fonts", "PressStart2P.ttf")
        try:
            self.font_file = fontfile
            self.font_lg   = ImageFont.truetype(fontfile, 72)
            self.font_md   = ImageFont.truetype(fontfile, 54)
        except OSError:
            logger.warning("Could not load PressStart2P – falling back")
            self.font_file = None
            self.font_lg = self.font_md = ImageFont.load_default()


        cfg             = ConfigManager()
        self.rarity_cfg = cfg.get_config("data/config/rarity_visuals") or {}
        self.icon_cfg   = cfg.get_config("data/config/stat_icons")     or {}


        sheet_path = os.path.join(assets_base, self.icon_cfg.get("sprite_sheet", ""))
        self.sheet = (
            Image.open(sheet_path).convert("RGBA")
            if os.path.isfile(sheet_path)
            else None
        )
        self.tile = self.icon_cfg.get("tile_size", 32)


    # ───────────────────── helper methods ─────────────────────
    @staticmethod
    def _hex(h: str) -> Tuple[int, int, int]:
        h = h.lstrip("#")
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4)) if len(h) == 6 else (255, 255, 255)


    @lru_cache(maxsize=256)
    def _slice_icon(self, col: int, row: int) -> Image.Image:
        if not self.sheet:
            return Image.new("RGBA", ICON_SIZE, (0, 0, 0, 0))
        x0, y0 = col * self.tile, row * self.tile
        return (
            self.sheet.crop((x0, y0, x0 + self.tile, y0 + self.tile))
            .resize(ICON_SIZE, Image.Resampling.NEAREST)
        )


    def _icon_coords(self, key: str):
        icons = self.icon_cfg.get("icons", {})
        return icons.get(key.lower().replace(" ", "")) or icons.get(key.lower())


    # dominant-colour helpers
    def _dominant(self, img):  # type: ignore[return-value]
        px = [p for p in img.getdata() if p[3] > 0]
        return (255, 255, 255) if not px else Counter(px).most_common(1)[0][0][:3]


    def _usable(self, rgb):
        r, g, b = rgb
        bright  = (r + g + b) / 3
        return bright >= BRIGHT_MIN and colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)[1] >= SAT_MIN


    @staticmethod
    def _blend(a, b, t=0.5):
        return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


    def _sprite_glow(self, sprite, rarity_rgb):
        dom = self._dominant(sprite)
        glow_rgb = dom if self._usable(dom) else rarity_rgb
        if BLEND_WITH_RARITY and self._usable(dom):
            glow_rgb = self._blend(dom, rarity_rgb)
        glow = Image.new("RGBA", sprite.size, (*glow_rgb, 255))
        glow.putalpha(sprite.split()[-1])
        glow = glow.filter(ImageFilter.GaussianBlur(18))
        out  = Image.new("RGBA", sprite.size, (0, 0, 0, 0))
        out.paste(glow, (0, 0), glow)
        out.paste(sprite, (0, 0), sprite)
        return out


    # ───────────────────── public API ─────────────────────
    async def render_esprit_detail_image(
        self,
        esprit_data: dict | None = None,
        esprit_instance=None,
        include_description: bool = False,
        esprit_data_dict: dict | None = None,
    ) -> Image.Image:
        esprit_data = esprit_data or esprit_data_dict or {}


        # ── sprite load & centre ───────────────────────
        raw = Image.open(
            os.path.join(self.assets_base, esprit_data.get("visual_asset_path", ""))
        ).convert("RGBA")
        bbox   = raw.getbbox()
        sprite = raw.crop(bbox) if bbox else raw
        w, h   = sprite.size
        scale  = min(SPRITE_H / w, SPRITE_H / h)
        sprite = sprite.resize((int(w * scale), int(h * scale)), Image.Resampling.NEAREST)
        centred = Image.new("RGBA", (SPRITE_H, SPRITE_H), (0, 0, 0, 0))
        centred.paste(sprite, ((SPRITE_H - sprite.width) // 2, (SPRITE_H - sprite.height) // 2), sprite)
        sprite = centred


        rarity     = esprit_data.get("rarity", "Common")
        rarity_rgb = self._hex(self.rarity_cfg.get(rarity, {}).get("color", "#FFFFFF"))
        sprite     = self._sprite_glow(sprite, rarity_rgb)


        # ── canvas ─────────────────────────────────────
        H = PAD + SPRITE_H + 30 + self.font_lg.size + 20 + self.font_md.size * 2 + 40 + ROW_H * 5 + PAD
        base = Image.new("RGBA", (CANVAS_W, H), (30, 30, 30, 255))
        draw = ImageDraw.Draw(base)


        # border + vignette
        draw.rectangle(
            [0, 0, CANVAS_W - 1, H - 1],
            outline=(*self._hex(self.rarity_cfg.get(rarity, {}).get("border_color", "#A9A9A9")), 255),
            width=8,
        )
        vign = Image.new("L", base.size, 0)
        ImageDraw.Draw(vign).ellipse((-CANVAS_W * 0.2, -H * 0.1, CANVAS_W * 1.2, H * 1.5), fill=255)
        base = Image.composite(
            base, Image.new("RGBA", base.size, (10, 10, 10, 255)), vign.filter(ImageFilter.GaussianBlur(250))
        )
        draw = ImageDraw.Draw(base)


        base.paste(sprite, ((CANVAS_W - SPRITE_H) // 2, PAD), sprite)


        # ── headings ───────────────────────────────────
        y  = PAD + SPRITE_H + 30
        cx = CANVAS_W // 2


        # dynamic name sizing
        name       = esprit_data.get("name", "Unknown")
        name_font  = self.font_lg
        if self.font_file:
            while (
                ImageDraw.Draw(Image.new("RGBA", (1, 1))).textlength(name, font=name_font)
                > CANVAS_W - 80
                and name_font.size > 32
            ):
                name_font = ImageFont.truetype(self.font_file, name_font.size - 4)
        draw.text((cx, y), name, font=name_font, fill="white", anchor="mt", stroke_width=1, stroke_fill="black")
        y += name_font.size + 20


        draw.text((cx, y), f"Rarity: {rarity}", font=self.font_md, fill=rarity_rgb,
                  anchor="mt", stroke_width=1, stroke_fill="black")
        y += self.font_md.size + 20


        draw.text((cx, y), f"Level: {esprit_instance.current_level}", font=self.font_md,
                  fill=(200, 200, 255, 255), anchor="mt")
        y += self.font_md.size + 20


        # ── stats data ─────────────────────────────────
        left_stats = [
            ("HP",  esprit_instance.current_hp),
            ("ATK", esprit_data["base_attack"]),
            ("DEF", esprit_data["base_defense"]),
            ("SPD", esprit_data["base_speed"]),
            ("MP",  esprit_data.get("base_mana", 0)),
        ]
        right_stats = [
            ("MR",     esprit_data.get("base_magic_resist", 0)),
            ("CRIT",   f"{esprit_data.get('base_crit_rate', 0)*100:.1f}%"),
            ("BLOCK",  f"{esprit_data.get('base_block_rate', 0)*100:.1f}%"),
            ("DODGE",  f"{esprit_data.get('base_dodge_chance', 0)*100:.1f}%"),
            ("MP REG", esprit_data.get("base_mana_regen", 0)),
        ]


        bar_x    = CANVAS_W // 2
        half_pad = (ROW_H - ICON_SIZE[1]) // 2


        # column X positions
        icon_L_x = bar_x - COL_GAP_L
        icon_R_x = bar_x + COL_GAP_R
        val_L_x  = icon_L_x + ICON_SIZE[0] + TEXT_PAD
        val_R_x  = icon_R_x + ICON_SIZE[0] + TEXT_PAD


        # ── draw rows ──────────────────────────────────
        for i, ((lk, lv), (rk, rv)) in enumerate(zip(left_stats, right_stats)):
            row_top   = y + i * ROW_H
            row_mid_y = row_top + ROW_H // 2


            # left
            if coords := self._icon_coords(lk):
                icon = self._slice_icon(*coords)
                base.paste(icon, (icon_L_x, row_top + half_pad), icon)
            draw.text((val_L_x, row_mid_y), str(lv),
                      font=self.font_md, fill="white", anchor="lm")


            # right
            if coords := self._icon_coords(rk):
                icon = self._slice_icon(*coords)
                base.paste(icon, (icon_R_x, row_top + half_pad), icon)
            draw.text((val_R_x, row_mid_y), str(rv),
                      font=self.font_md, fill="white", anchor="lm")


        return base

