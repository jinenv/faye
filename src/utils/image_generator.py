# This is the complete file content for src/utils/image_generator.py

from PIL import Image, ImageDraw, ImageFont
import os
import io

from src.utils.logger import get_logger
from src.utils.config_manager import ConfigManager

logger = get_logger(__name__)

class ImageGenerator:
    def __init__(self, assets_base_path="assets/"):
        self.assets_base_path = assets_base_path
        self.companion_assets_path = os.path.join(assets_base_path, "companions")
        self.ui_assets_path = os.path.join(assets_base_path, "ui")
        self.font_path = os.path.abspath(os.path.join(self.ui_assets_path, "fonts", "PressStart2P.ttf"))

        try:
            self.font_small = ImageFont.truetype(self.font_path, 40)
            self.font_medium = ImageFont.truetype(self.font_path, 52)
            self.font_large = ImageFont.truetype(self.font_path, 68)
            self.font_description = ImageFont.truetype(self.font_path, 32)
            self.font_bar_text = ImageFont.truetype(self.font_path, 28)
            logger.info(f"Fonts loaded successfully from: {self.font_path}")
        except IOError as e:
            logger.error(f"Error: Font file not found at '{self.font_path}'. Details: {e}", exc_info=True)
            self.font_small = self.font_medium = self.font_large = self.font_description = self.font_bar_text = ImageFont.load_default()

        try:
            bars_path = os.path.join(self.ui_assets_path, "bars")
            self.bar_standard_bg = Image.open(os.path.join(bars_path, "empty_bar.png")).convert("RGBA")
            self.bar_boss_bg = Image.open(os.path.join(bars_path, "boss_empty_bar.png")).convert("RGBA")
            self.fill_xp = Image.open(os.path.join(bars_path, "xp_bar.png")).convert("RGBA")
            self.fill_hp = Image.open(os.path.join(bars_path, "hp_bar.png")).convert("RGBA")
            self.fill_mana = Image.open(os.path.join(bars_path, "mana_bar.png")).convert("RGBA")
            self.fill_boss_hp = Image.open(os.path.join(bars_path, "boss_hp_bar.png")).convert("RGBA")
            logger.info("All bar UI assets loaded successfully.")
        except FileNotFoundError as e:
            logger.error(f"Could not find one or more bar assets in '{bars_path}'. Details: {e}", exc_info=True)
            self.bar_standard_bg = self.bar_boss_bg = self.fill_xp = self.fill_hp = self.fill_mana = self.fill_boss_hp = None

        self.config_manager = ConfigManager()
        self.rarity_visuals = self.config_manager.get_config('rarity_visuals')

    def _hex_to_rgb(self, hex_color: str):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def _wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_width: int):
        lines = []
        if not text:
            return [""]
        words = text.split(' ')
        current_line = []
        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = font.getbbox(test_line)
            test_line_width = bbox[2] - bbox[0]
            if test_line_width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        if current_line:
            lines.append(' '.join(current_line))
        return lines

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

    async def render_esprit_detail_image(self, esprit_data_dict: dict, esprit_instance, include_description: bool = False):
        canvas_width = 800
        padding_top = 30
        padding_bottom = 40
        
        sprite_target_size = (512, 512)
        sprite_path = esprit_data_dict.get('visual_asset_path', 'esprits/default.png')
        esprit_sprite = await self._load_and_resize_sprite(sprite_path, target_size=sprite_target_size)
        sprite_x = (canvas_width - sprite_target_size[0]) // 2
        sprite_y = padding_top
        
        temp_img_for_text_calc = Image.new('RGBA', (1,1))
        temp_draw = ImageDraw.Draw(temp_img_for_text_calc)
        
        def get_text_height(text, font):
            bbox = temp_draw.textbbox((0,0), text, font=font, anchor="lt")
            return bbox[3] - bbox[1]

        current_y = sprite_y + sprite_target_size[1] + 30
        
        name = esprit_data_dict.get('name', 'Unknown')
        current_y += get_text_height(name, self.font_large) + 20

        rarity = esprit_data_dict.get('rarity', 'Common')
        current_y += get_text_height(f"Rarity: {rarity}", self.font_medium) + 20
        
        current_y += get_text_height(f"Level: {esprit_instance.current_level}", self.font_medium) + 40

        stats_start_y = current_y
        stat_line_height = 50
        num_stats_rows = 5
        current_y += num_stats_rows * stat_line_height + 40
        
        description_lines = []
        if include_description:
            description_text = esprit_data_dict.get('description', 'No description provided.')
            description_max_width = canvas_width - 140
            description_lines = self._wrap_text(description_text, self.font_description, description_max_width)
            description_height_total = 0
            for line in description_lines:
                description_height_total += get_text_height(line, self.font_description) + 8
            if description_lines: description_height_total -= 8
            current_y += description_height_total + 40

        xp_bar_y_start = current_y
        desired_bar_width_for_calc = 600
        bar_height_for_calc = 40
        if self.bar_standard_bg:
            original_bar_width_asset, original_bar_height_asset = self.bar_standard_bg.size
            if original_bar_width_asset > 0:
                scale_factor = desired_bar_width_for_calc / original_bar_width_asset
                bar_height_for_calc = int(original_bar_height_asset * scale_factor)
            else:
                 bar_height_for_calc = original_bar_height_asset if original_bar_height_asset > 0 else 40
        current_y += bar_height_for_calc + padding_bottom
        
        canvas_height = current_y
        img = Image.new('RGBA', (canvas_width, canvas_height), (30, 30, 30, 255))
        draw = ImageDraw.Draw(img)
        
        rarity_info = self.rarity_visuals.get(rarity, {})
        border_hex_color = rarity_info.get('border_color', 'A9A9A9')
        border_rgb_color = self._hex_to_rgb(border_hex_color) + (255,)
        draw.rectangle([0, 0, canvas_width-1, canvas_height-1], outline=border_rgb_color, width=8)

        img.paste(esprit_sprite, (sprite_x, sprite_y), esprit_sprite)

        # --- [CORRECTED TEXT CENTERING FUNCTION] ---
        def draw_centered_text_final(draw_obj, y_pos, text, font, fill_color):
            # Directly tell Pillow to center the text using the canvas midpoint and anchor "mt"
            # "mt" means the (x,y) point is the Middle-Top of the text bounding box
            draw_obj.text((canvas_width / 2, y_pos), text, font=font, fill=fill_color, anchor="mt")
        
        def draw_two_color_stat(draw_obj, x_start, y_pos, name_text, value_text, font, name_color, value_color):
            name_str = f"{name_text}:"
            draw_obj.text((x_start, y_pos), name_str, font=font, fill=name_color)
            name_bbox = font.getbbox(name_str)
            name_width = name_bbox[2] - name_bbox[0]
            value_x = x_start + name_width + 20
            draw_obj.text((value_x, y_pos), str(value_text), font=font, fill=value_color)

        text_y_draw = sprite_y + sprite_target_size[1] + 30
        rarity_color_text = self._hex_to_rgb(rarity_info.get('color', 'FFFFFF')) + (255,)
        
        draw_centered_text_final(draw, text_y_draw, name, self.font_large, (255, 255, 255, 255))
        text_y_draw += get_text_height(name, self.font_large) + 20
        
        draw_centered_text_final(draw, text_y_draw, f"Rarity: {rarity}", self.font_medium, rarity_color_text)
        text_y_draw += get_text_height(f"Rarity: {rarity}", self.font_medium) + 20
        
        draw_centered_text_final(draw, text_y_draw, f"Level: {esprit_instance.current_level}", self.font_medium, (200, 200, 255, 255))

        col1_x, col2_x = 100, 470
        stat_name_color, stat_value_color = (150, 150, 150, 255), (255, 255, 255, 255)
        stats_col1_data = [("HP", esprit_instance.current_hp), ("ATK", esprit_data_dict['base_attack']), ("DEF", esprit_data_dict['base_defense']), ("SPD", esprit_data_dict['base_speed']), ("MP", esprit_data_dict.get('base_mana', 0))]
        stats_col2_data = [("MR", esprit_data_dict.get('base_magic_resist', 0)), ("CRIT", f"{esprit_data_dict.get('base_crit_rate', 0.0)*100:.1f}%"), ("BLOCK", f"{esprit_data_dict.get('base_block_rate', 0.0)*100:.1f}%"), ("DODGE", f"{esprit_data_dict.get('base_dodge_chance', 0.0)*100:.1f}%"), ("MP REG", esprit_data_dict.get('base_mana_regen', 0))]

        current_stat_draw_y = stats_start_y
        for i, (name_text, value) in enumerate(stats_col1_data):
            draw_two_color_stat(draw, col1_x, current_stat_draw_y + i * stat_line_height, name_text, value, self.font_small, stat_name_color, stat_value_color)
        for i, (name_text, value) in enumerate(stats_col2_data):
            draw_two_color_stat(draw, col2_x, current_stat_draw_y + i * stat_line_height, name_text, value, self.font_small, stat_name_color, stat_value_color)

        if include_description:
            current_desc_draw_y = stats_start_y + num_stats_rows * stat_line_height + 40
            for line in description_lines:
                draw.text((70, current_desc_draw_y), line, font=self.font_description, fill=(230, 230, 230, 255))
                current_desc_draw_y += get_text_height(line, self.font_description) + 8

        if self.bar_standard_bg and self.fill_xp:
            xp_max = esprit_instance.current_level * 100
            xp_current = esprit_instance.current_xp
            xp_percentage = xp_current / xp_max if xp_max > 0 else 0

            bar_asset_bg_orig = self.bar_standard_bg
            original_bar_width, original_bar_height = bar_asset_bg_orig.size
            desired_bar_width = 600
            
            final_bar_width, final_bar_height = desired_bar_width, original_bar_height
            resized_bar_bg = bar_asset_bg_orig
            resized_fill = self.fill_xp

            if original_bar_width > 0:
                scale_factor = desired_bar_width / original_bar_width
                desired_bar_height = int(original_bar_height * scale_factor)
                
                resized_bar_bg = bar_asset_bg_orig.resize((desired_bar_width, desired_bar_height), Image.Resampling.NEAREST)
                resized_fill = self.fill_xp.resize((desired_bar_width, desired_bar_height), Image.Resampling.NEAREST)
                final_bar_width, final_bar_height = desired_bar_width, desired_bar_height
            else:
                logger.warning("XP Bar background asset has zero width or not loaded.")
                final_bar_width, final_bar_height = original_bar_width, original_bar_height
            
            bar_x = (canvas_width - final_bar_width) // 2
            
            img.paste(resized_bar_bg, (bar_x, xp_bar_y_start), resized_bar_bg)

            fill_draw_width = int(final_bar_width * xp_percentage)
            if xp_current > 0 and fill_draw_width == 0: fill_draw_width = 1
            
            if fill_draw_width > 0:
                if fill_draw_width <= resized_fill.width and final_bar_height <= resized_fill.height:
                    cropped_fill = resized_fill.crop((0, 0, fill_draw_width, final_bar_height))
                    img.paste(cropped_fill, (bar_x, xp_bar_y_start), cropped_fill)
                else:
                    logger.warning(f"XP Bar fill crop dims invalid. Fill: {resized_fill.size}, Crop: (0,0,{fill_draw_width},{final_bar_height})")

            xp_text = f"{xp_current} / {xp_max}"
            text_x = bar_x + (final_bar_width / 2)
            text_y = xp_bar_y_start + (final_bar_height / 2)
            
            outline_color = "black"
            for dx_outline in [-1, 0, 1]: # Simplified stroke, or use a loop as before
                for dy_outline in [-1, 0, 1]:
                    if dx_outline == 0 and dy_outline == 0: continue # Skip center for outline
                    # For a fuller stroke, you might draw more points or a slightly larger font in black
                    draw.text((text_x + dx_outline, text_y + dy_outline), xp_text, font=self.font_bar_text, fill=outline_color, anchor="mm")
            draw.text((text_x, text_y), xp_text, font=self.font_bar_text, fill="white", anchor="mm")
        else:
            logger.warning("XP Bar assets (background or fill) not loaded, skipping XP bar rendering.")
            
        return img