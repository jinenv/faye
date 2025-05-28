from PIL import Image, ImageDraw, ImageFont
import os
from src.utils.logger import Logger
from src.utils.config_manager import ConfigManager

log = Logger(__name__)

# --- Configuration for Image Generation ---
# Target size for individual sprites when rendered in embeds
TARGET_SPRITE_SIZE = (128, 128)
# Font settings
FONT_PATH = "assets/ui/fonts/PressStart2P.ttf" # Path to your font
FONT_SIZE_BODY = 14
FONT_SIZE_TITLE = 18

# --- Helper to load and resize font ---
def get_font(size: int = FONT_SIZE_BODY):
    try:
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_file_dir, '..', '..'))
        full_font_path = os.path.join(project_root, FONT_PATH)
        # log.debug(f"Attempting to load font from: {full_font_path}") # Use debug to avoid spamming logs
        return ImageFont.truetype(full_font_path, size)
    except IOError as e:
        log.error(f"FONT ERROR: Font file NOT FOUND or UNREADABLE at: {full_font_path}. Using default font. Error: {e}", exc_info=True)
        return ImageFont.load_default()
    except Exception as e:
        log.error(f"FONT ERROR: Unexpected error loading font from {full_font_path}: {e}", exc_info=True)
        return ImageFont.load_default()

# --- NEW Helper to load and resize sprites ---
def _load_and_resize_sprite(relative_asset_path: str, target_size: tuple = TARGET_SPRITE_SIZE) -> Image.Image:
    """
    Loads an image from a relative asset path, converts it to RGBA,
    and resizes it to the target_size using NEAREST neighbor for pixel art.
    """
    current_file_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_file_dir, '..', '..'))
    full_asset_path = os.path.join(project_root, relative_asset_path)

    if not os.path.exists(full_asset_path):
        log.error(f"ASSET NOT FOUND: Image file missing at: '{full_asset_path}'.")
        return None

    try:
        img = Image.open(full_asset_path).convert("RGBA")
        # Use Image.NEAREST for pixel art scaling to avoid blurriness
        img = img.resize(target_size, Image.Resampling.NEAREST)
        return img
    except Exception as e:
        log.error(f"IMAGE PROCESSING ERROR: Could not load or resize image '{full_asset_path}': {e}", exc_info=True)
        return None

# --- Renamed and adapted from previous render_class_selection_page_image ---
def render_esprit_selection_page_image(esprit_ids_on_page: list) -> Image.Image:
    """
    Renders a single image with multiple Esprit previews spliced together for selection pages.
    Each Esprit will be rendered at TARGET_SPRITE_SIZE.
    """
    log.info(f"Starting render for Esprit selection page with IDs: {esprit_ids_on_page}")
    esprit_data_config = ConfigManager.get_config('config', 'companions.json') # Using companions.json for Esprits
    if not esprit_data_config:
        log.error("render_esprit_selection_page_image: Failed to load companions.json. Returning None.")
        return None

    num_esprits = len(esprit_ids_on_page)
    if num_esprits == 0:
        log.warning("render_esprit_selection_page_image: No Esprit IDs provided. Returning blank image.")
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    # Layout parameters
    SPRITE_WIDTH, SPRITE_HEIGHT = TARGET_SPRITE_SIZE
    PADDING_X = 20 # Horizontal padding between sprites
    PADDING_Y = 10 # Vertical padding below sprite for text
    TEXT_HEIGHT = FONT_SIZE_BODY # Approximate height for a single line of text

    total_width = (SPRITE_WIDTH * num_esprits) + (PADDING_X * (num_esprits - 1))
    # Canvas height needs to accommodate sprite + name + some margin
    canvas_height = SPRITE_HEIGHT + PADDING_Y + TEXT_HEIGHT + 10

    combined_img = Image.new("RGBA", (total_width, canvas_height), (0, 0, 0, 0)) # Transparent background
    draw = ImageDraw.Draw(combined_img)
    font = get_font(FONT_SIZE_BODY)

    x_offset = 0
    images_successfully_loaded = 0
    for esprit_id in esprit_ids_on_page:
        esprit_info = esprit_data_config.get(esprit_id)
        if not esprit_info:
            log.warning(f"Esprit info not found for ID: '{esprit_id}'. Skipping. (Check companions.json).")
            x_offset += SPRITE_WIDTH + PADDING_X
            continue

        asset_path_relative = esprit_info.get('visual_asset_path', '')
        if not asset_path_relative:
            log.error(f"visual_asset_path is empty for Esprit '{esprit_id}'. Skipping.")
            x_offset += SPRITE_WIDTH + PADDING_X
            continue

        esprit_img = _load_and_resize_sprite(asset_path_relative, TARGET_SPRITE_SIZE)
        if esprit_img:
            combined_img.paste(esprit_img, (x_offset, 0), esprit_img)
            images_successfully_loaded += 1

            # Draw Esprit Name
            text_label = esprit_info['name']
            # Get text bounding box for accurate centering
            text_bbox = draw.textbbox((0,0), text_label, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_x = x_offset + (SPRITE_WIDTH - text_width) // 2
            draw.text((text_x, SPRITE_HEIGHT + PADDING_Y), text_label, font=font, fill=(255, 255, 255)) # White text

            x_offset += SPRITE_WIDTH + PADDING_X
        else:
            x_offset += SPRITE_WIDTH + PADDING_X # Move offset even if image fails to load

    if images_successfully_loaded == 0:
        log.error("No Esprit images were successfully loaded or combined for the selection page. Returning None.")
        return None

    log.info(f"Finished rendering Esprit selection page. Successfully loaded {images_successfully_loaded} images.")
    return combined_img


# --- Renamed and adapted from previous render_class_detail_image ---
def render_esprit_detail_image(esprit_id: str) -> Image.Image:
    """
    Renders a detailed image for a single Esprit, including its sprite and basic stats.
    The Esprit's sprite will be rendered at TARGET_SPRITE_SIZE.
    """
    log.info(f"Starting render for detail of Esprit: '{esprit_id}'")
    esprit_data_config = ConfigManager.get_config('config', 'companions.json')
    esprit_info = esprit_data_config.get(esprit_id)
    if not esprit_info:
        log.error(f"Esprit info not found for detail rendering: '{esprit_id}'. Returning None.")
        return None

    asset_path_relative = esprit_info.get('visual_asset_path', '')
    if not asset_path_relative:
        log.error(f"visual_asset_path is empty for Esprit '{esprit_id}' in detail rendering. Returning None.")
        return None

    # Load and resize the main Esprit sprite to TARGET_SPRITE_SIZE
    esprit_sprite = _load_and_resize_sprite(asset_path_relative, TARGET_SPRITE_SIZE)
    if not esprit_sprite:
        log.error(f"Failed to load or process sprite for Esprit '{esprit_id}' for detail view. Returning None.")
        return None

    # --- Define Canvas and Layout ---
    CANVAS_WIDTH = 500
    CANVAS_HEIGHT = max(esprit_sprite.height + 40, 250) # Ensure enough height for sprite + text

    detail_img = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0)) # Transparent background
    draw = ImageDraw.Draw(detail_img)

    font_title = get_font(FONT_SIZE_TITLE)
    font_body = get_font(FONT_SIZE_BODY)

    # Paste Esprit sprite (positioned for visual appeal)
    sprite_x = 20
    sprite_y = 20
    detail_img.paste(esprit_sprite, (sprite_x, sprite_y), esprit_sprite)

    # --- Draw Text Information ---
    text_start_x = sprite_x + esprit_sprite.width + 30 # Start text to the right of the sprite
    text_current_y = sprite_y + 10 # Start text slightly below sprite top

    # Name and Rarity
    draw.text((text_start_x, text_current_y), esprit_info['name'], font=font_title, fill=(255, 255, 255)) # White name
    text_current_y += FONT_SIZE_TITLE + 5

    rarity_emoji = ConfigManager.get_config('config', 'rarity_tiers.json').get(esprit_info['rarity'], {}).get('emoji', '')
    rarity_color_hex = ConfigManager.get_config('config', 'rarity_visuals.json').get(esprit_info['rarity'], "#FFFFFF")
    rarity_color_rgb = tuple(int(rarity_color_hex.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)) + (255,) # Convert hex to RGBA tuple

    draw.text((text_start_x, text_current_y), f"{rarity_emoji} {esprit_info['rarity']}", font=font_body, fill=rarity_color_rgb)
    text_current_y += FONT_SIZE_BODY + 15

    # Description (simple for now, might need wrapping for longer text)
    draw.text((text_start_x, text_current_y), esprit_info['description'], font=font_body, fill=(200, 200, 200))
    text_current_y += FONT_SIZE_BODY + 20

    # Base Stats
    draw.text((text_start_x, text_current_y), "Base Stats:", font=font_body, fill=(255, 255, 0)) # Yellow for stats header
    text_current_y += FONT_SIZE_BODY + 5

    stats_text = (
        f"HP: {esprit_info['base_hp']}\n"
        f"ATK: {esprit_info['base_attack']}\n"
        f"DEF: {esprit_info['base_defense']}\n"
        f"SPD: {esprit_info['base_speed']}\n"
        f"M.RES: {esprit_info['base_magic_resist']}\n"
        f"CRIT: {esprit_info['base_crit_rate'] * 100:.0f}%\n"
        f"BLOCK: {esprit_info['base_block_rate'] * 100:.0f}%\n"
        f"DODGE: {esprit_info['base_dodge_chance'] * 100:.0f}%\n"
        f"MANA REG: {esprit_info['base_mana_regen']}"
    )
    draw.text((text_start_x, text_current_y), stats_text, font=font_body, fill=(255, 255, 255)) # White stats

    log.info(f"Finished rendering detail image for '{esprit_id}'.")
    return detail_img