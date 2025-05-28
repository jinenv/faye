from PIL import Image, ImageDraw, ImageFont
import os
from src.utils.logger import Logger
from src.utils.config_manager import ConfigManager

log = Logger(__name__)

CLASS_PREVIEW_SIZE = (200, 200)
CLASS_PREVIEW_PADDING = 20
TEXT_OFFSET_Y = 10
FONT_PATH = "assets/ui/fonts/PressStart2P.ttf" # Path to your font (ensure this is correct)
FONT_SIZE = 16

def get_font(size: int = FONT_SIZE):
    try:
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_file_dir, '..', '..'))
        full_font_path = os.path.join(project_root, FONT_PATH)
        log.info(f"DEBUG_FONT: Attempting to load font from: {full_font_path}")
        return ImageFont.truetype(full_font_path, size)
    except IOError as e: # Catch IOError specifically for font loading
        log.error(f"FONT ERROR: Font file NOT FOUND or UNREADABLE at: {full_font_path}. Using default font. Error: {e}", exc_info=True)
        return ImageFont.load_default()
    except Exception as e:
        log.error(f"FONT ERROR: Unexpected error loading font from {full_font_path}: {e}", exc_info=True)
        return ImageFont.load_default()


def render_class_selection_page_image(class_ids_on_page: list) -> Image.Image:
    """
    Renders a single image with multiple class previews spliced together for class selection pages.
    """
    log.info(f"DEBUG_IMG_RENDER: Starting render for page with IDs: {class_ids_on_page}")
    class_data_config = ConfigManager.get_config('config', 'class_data.json')
    if not class_data_config:
        log.error("render_class_selection_page_image: Failed to load class_data.json. Returning None.")
        return None

    num_classes = len(class_ids_on_page)
    if num_classes == 0:
        log.warning("render_class_selection_page_image: No class IDs provided. Returning blank image.")
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    total_width = (CLASS_PREVIEW_SIZE[0] * num_classes) + (CLASS_PREVIEW_PADDING * (num_classes - 1))
    canvas_height = CLASS_PREVIEW_SIZE[1] + FONT_SIZE + TEXT_OFFSET_Y + 10

    combined_img = Image.new("RGBA", (total_width, canvas_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(combined_img)
    font = get_font()

    x_offset = 0
    images_successfully_loaded = 0
    for class_id in class_ids_on_page:
        class_info = class_data_config.get(class_id)
        if not class_info:
            log.warning(f"render_class_selection_page_image: Class info not found for ID: '{class_id}'. Skipping. (Check class_data.json).")
            x_offset += CLASS_PREVIEW_SIZE[0] + CLASS_PREVIEW_PADDING
            continue

        asset_path_relative = class_info.get('visual_asset_path', '')
        if not asset_path_relative:
            log.error(f"render_class_selection_page_image: visual_asset_path is empty for class '{class_id}'. Skipping. (Check class_data.json).")
            x_offset += CLASS_PREVIEW_SIZE[0] + CLASS_PREVIEW_PADDING
            continue

        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_file_dir, '..', '..'))
        full_asset_path = os.path.join(project_root, asset_path_relative)

        log.info(f"DEBUG_IMG_RENDER: Attempting to load asset for '{class_id}' from: {full_asset_path}")
        if not os.path.exists(full_asset_path):
            log.error(f"render_class_selection_page_image: Class asset file NOT FOUND for '{class_id}' at: '{full_asset_path}'. Skipping. (Check file path and name).", exc_info=True)
            x_offset += CLASS_PREVIEW_SIZE[0] + CLASS_PREVIEW_PADDING
            continue

        try:
            class_img = Image.open(full_asset_path).convert("RGBA").resize(CLASS_PREVIEW_SIZE)
            combined_img.paste(class_img, (x_offset, 0), class_img)
            images_successfully_loaded += 1

            text_label = class_info['name']
            text_width, text_height = draw.textbbox((0,0), text_label, font=font)[2:]
            text_x = x_offset + (CLASS_PREVIEW_SIZE[0] - text_width) // 2
            draw.text((text_x, CLASS_PREVIEW_SIZE[1] + TEXT_OFFSET_Y), text_label, font=font, fill=(255, 255, 255))

            x_offset += CLASS_PREVIEW_SIZE[0] + CLASS_PREVIEW_PADDING
        except Exception as e:
            log.error(f"render_class_selection_page_image: Error processing image for '{class_id}' at '{full_asset_path}': {e}. Skipping.", exc_info=True)
            x_offset += CLASS_PREVIEW_SIZE[0] + CLASS_PREVIEW_PADDING

    if images_successfully_loaded == 0:
        log.error("render_class_selection_page_image: No images were successfully loaded or combined. Returning None.")
        return None

    log.info(f"DEBUG_IMG_RENDER: Finished rendering page. Successfully loaded {images_successfully_loaded} images.")
    return combined_img


def render_class_detail_image(class_id: str) -> Image.Image:
    """
    Renders a detailed image for a single class, possibly showing stats visually.
    """
    log.info(f"DEBUG_IMG_DETAIL: Starting render for detail of class: '{class_id}'")
    class_data_config = ConfigManager.get_config('config', 'class_data.json')
    class_info = class_data_config.get(class_id)
    if not class_info:
        log.error(f"render_class_detail_image: Class info not found for detail rendering: '{class_id}'. Returning None.")
        return None

    asset_path_relative = class_info.get('visual_asset_path', '')
    if not asset_path_relative:
        log.error(f"render_class_detail_image: visual_asset_path is empty for class '{class_id}' in detail rendering. Returning None.")
        return None

    current_file_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_file_dir, '..', '..'))
    full_asset_path = os.path.join(project_root, asset_path_relative)

    log.info(f"DEBUG_IMG_DETAIL: Checking detail asset for '{class_id}' at path: {full_asset_path}")
    if not os.path.exists(full_asset_path):
        log.error(f"render_class_detail_image: Class asset file NOT FOUND for detail '{class_id}' at: '{full_asset_path}'. Returning None. (Check file path and name).", exc_info=True)
        return None

    try:
        base_img = Image.open(full_asset_path).convert("RGBA").resize((300, 300))

        detail_img_width = 600
        detail_img_height = max(base_img.height, 350)
        detail_img = Image.new("RGBA", (detail_img_width, detail_img_height), (0, 0, 0, 200))

        detail_img.paste(base_img, (20, 20), base_img)

        draw = ImageDraw.Draw(detail_img)
        font_large = get_font(size=24)
        font_small = get_font(size=16)

        draw.text((340, 30), class_info['name'], font=font_large, fill=(255, 255, 255))
        # Text wrapping for description if needed, otherwise it will just be a long line
        draw.text((340, 70), class_info['description'], font=font_small, fill=(200, 200, 200))

        stat_y_start = 150
        stat_x = 340
        draw.text((stat_x, stat_y_start), f"HP: {class_info['base_hp']}", font=font_small, fill=(0, 255, 0))
        draw.text((stat_x, stat_y_start + 25), f"ATK: {class_info['base_attack']}", font=font_small, fill=(255, 0, 0))
        draw.text((stat_x, stat_y_start + 50), f"DEF: {class_info['base_defense']}", font=font_small, fill=(0, 0, 255))
        draw.text((stat_x, stat_y_start + 75), f"SPD: {class_info['base_speed']}", font=font_small, fill=(255, 255, 0))

        log.info(f"DEBUG_IMG_DETAIL: Finished rendering detail image for '{class_id}'.")
        return detail_img
    except Exception as e:
        log.error(f"render_class_detail_image: Error processing detail image for '{class_id}': {e}. Returning None.", exc_info=True)
        return None