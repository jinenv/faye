# src/utils/image_generator.py
from PIL import Image, ImageDraw, ImageFont, ImageOps
import os
import io
import math

# Corrected import for the logger
from src.utils.logger import get_logger
from src.utils.config_manager import ConfigManager # <--- ADD THIS IMPORT

logger = get_logger(__name__)

class ImageGenerator:
    def __init__(self, assets_base_path="assets/"):
        self.assets_base_path = assets_base_path
        self.companion_assets_path = os.path.join(assets_base_path, "companions")
        self.ui_assets_path = os.path.join(assets_base_path, "ui")

        self.font_path = os.path.abspath(os.path.join(self.ui_assets_path, "fonts", "PressStart2P.ttf"))

        # FONT SIZE CHANGES FOR MAX TEXT VISIBILITY
        try:
            self.font_small = ImageFont.truetype(self.font_path, 40)
            self.font_medium = ImageFont.truetype(self.font_path, 52)
            self.font_large = ImageFont.truetype(self.font_path, 68)
            logger.info(f"Fonts loaded successfully from: {self.font_path}")
        except IOError as e:
            logger.error(f"Error: Font file not found or inaccessible at '{self.font_path}'. Error details: {e}", exc_info=True)
            self.font_small = ImageFont.load_default()
            self.font_medium = ImageFont.load_default()
            self.font_large = ImageFont.load_default()

        # --- NEW: Load rarity visuals for colors ---
        self.config_manager = ConfigManager() # Instantiate ConfigManager
        self.rarity_visuals = self.config_manager.get_config('rarity_visuals')
        # --- END NEW ---

    # Helper to convert hex to RGB
    def _hex_to_rgb(self, hex_color: str):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


    async def _load_and_resize_sprite(self, sprite_path: str, target_size=(128, 128)):
        full_path = os.path.join(self.assets_base_path, sprite_path)
        if not os.path.exists(full_path):
            logger.warning(f"Sprite not found: {full_path}. Returning blank image.")
            return Image.new('RGBA', target_size, (0, 0, 0, 0))

        try:
            with Image.open(full_path) as img:
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                resized_img = img.resize(target_size, Image.Resampling.NEAREST)
                return resized_img
        except Exception as e:
            logger.error(f"Failed to load or resize sprite from {full_path}: {e}", exc_info=True)
            return Image.new('RGBA', target_size, (255, 0, 0, 128))


    async def render_esprit_selection_page_image(self, esprits_data_list: list):
        pass

    async def render_esprit_detail_image(self, esprit_data_dict: dict, esprit_instance):
        canvas_width = 800
        canvas_height = 1250
        img = Image.new('RGBA', (canvas_width, canvas_height), (30, 30, 30, 255))
        draw = ImageDraw.Draw(img)

        # --- MODIFIED: Draw rarity-colored border ---
        rarity = esprit_data_dict.get('rarity', 'Common')
        # Fetch color from loaded rarity_visuals, default to dark gray if not found
        rarity_info = self.rarity_visuals.get(rarity, {})
        border_hex_color = rarity_info.get('border_color', 'A9A9A9')
        border_rgb_color = self._hex_to_rgb(border_hex_color) + (255,) # Add alpha channel

        draw.rectangle([0, 0, canvas_width-1, canvas_height-1], outline=border_rgb_color, width=8) # Increased border width to 8 for visibility
        # --- END MODIFIED ---

        # --- Esprit Sprite (Centered at top) ---
        sprite_target_size = (512, 512)
        sprite_path = esprit_data_dict.get('visual_asset_path', 'esprits/default.png')
        esprit_sprite = await self._load_and_resize_sprite(sprite_path, target_size=sprite_target_size)

        sprite_x = (canvas_width - sprite_target_size[0]) // 2
        sprite_y = 30
        img.paste(esprit_sprite, (sprite_x, sprite_y), esprit_sprite)

        # --- Esprit Name, Rarity, Level (Centered below sprite) ---
        def draw_centered_text(draw_obj, y_pos, text, font, fill_color):
            left, top, right, bottom = font.getbbox(text)
            text_width = right - left
            centered_x = (canvas_width - text_width) // 2
            draw_obj.text((centered_x, y_pos), text, font=font, fill=fill_color)

        current_y = sprite_y + sprite_target_size[1] + 30

        name = esprit_data_dict.get('name', 'Unknown')
        rarity = esprit_data_dict.get('rarity', 'Common')
        # Existing rarity_colors for text, might need to be sourced from rarity_visuals too
        rarity_colors = {
            "Supreme": (255, 215, 0, 255), "Mythic": (148, 0, 211, 255), "Legendary": (255, 140, 0, 255),
            "Epic": (128, 0, 128, 255), "Rare": (0, 0, 255, 255), "Uncommon": (0, 200, 0, 255),
            "Common": (169, 169, 169, 255)
        }
        rarity_color_text = rarity_colors.get(rarity, (255, 255, 255, 255)) # Used for text color

        draw_centered_text(draw, current_y, name, self.font_large, (255, 255, 255, 255))
        current_y += (self.font_large.getbbox(name)[3] - self.font_large.getbbox(name)[1]) + 20

        draw_centered_text(draw, current_y, f"Rarity: {rarity}", self.font_medium, rarity_color_text)
        current_y += (self.font_medium.getbbox(f"Rarity: {rarity}")[3] - self.font_medium.getbbox(f"Rarity: {rarity}")[1]) + 20

        draw_centered_text(draw, current_y, f"Level: {esprit_instance.current_level}", self.font_medium, (200, 200, 255, 255))
        current_y += (self.font_medium.getbbox(f"Level: {esprit_instance.current_level}")[3] - self.font_medium.getbbox(f"Level: {esprit_instance.current_level}")[1]) + 70

        # --- Stats (Two closer columns, color-coded) ---
        col1_x = 100
        col2_x = 470

        stat_line_height = 60

        stat_name_color = (150, 150, 150, 255)
        stat_value_color = (255, 255, 255, 255)

        def draw_two_color_stat(draw_obj, x_start, y_pos, name_text, value_text, font, name_color, value_color):
            name_str = f"{name_text}:"
            draw_obj.text((x_start, y_pos), name_str, font=font, fill=name_color)

            name_bbox = font.getbbox(name_str)
            name_width = name_bbox[2] - name_bbox[0]
            value_x = x_start + name_width + 20

            draw_obj.text((value_x, y_pos), str(value_text), font=font, fill=value_color)

        stats_col1_data = [
            ("HP", esprit_instance.current_hp),
            ("ATK", esprit_data_dict['base_attack']),
            ("DEF", esprit_data_dict['base_defense']),
            ("SPD", esprit_data_dict['base_speed']),
            ("MP", esprit_data_dict.get('base_mana', 0))
        ]
        stats_col2_data = [
            ("MR", esprit_data_dict.get('base_magic_resist', 0)),
            ("CRIT", f"{esprit_data_dict.get('base_crit_rate', 0.0)*100:.1f}%"),
            ("BLOCK", f"{esprit_data_dict.get('base_block_rate', 0.0)*100:.1f}%"),
            ("DODGE", f"{esprit_data_dict.get('base_dodge_chance', 0.0)*100:.1f}%"),
            ("MP REG", esprit_data_dict.get('base_mana_regen', 0))
        ]

        for i, (name_text, value) in enumerate(stats_col1_data):
            draw_two_color_stat(draw, col1_x, current_y + i * stat_line_height, name_text, value, self.font_small, stat_name_color, stat_value_color)

        for i, (name_text, value) in enumerate(stats_col2_data):
            draw_two_color_stat(draw, col2_x, current_y + i * stat_line_height, name_text, value, self.font_small, stat_name_color, stat_value_color)

        current_y += max(len(stats_col1_data), len(stats_col2_data)) * stat_line_height + 50

        # --- XP Bar (Centered at bottom) ---
        xp_max = esprit_instance.current_level * 100
        xp_current = esprit_instance.current_xp
        xp_percentage = xp_current / xp_max if xp_max > 0 else 0

        bar_width = 700
        bar_height = 40
        bar_x = (canvas_width - bar_width) // 2
        bar_y = current_y

        draw.rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], fill=(50, 50, 50, 255), outline=(100, 100, 100, 255))
        draw.rectangle([bar_x, bar_y, bar_x + (bar_width * xp_percentage), bar_y + bar_height], fill=(0, 200, 0, 255))
        xp_text = f"XP: {xp_current}/{xp_max}"
        draw.text((bar_x + bar_width / 2, bar_y + bar_height / 2), xp_text, font=self.font_large, fill=(255, 255, 255, 255), anchor="mm")

        return img