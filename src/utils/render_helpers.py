# src/utils/render_helpers.py
import os
import discord
from PIL import Image
import io

# Corrected import for the logger
from src.utils.logger import get_logger

logger = get_logger(__name__) # Initialize logger with get_logger

def render_pil_to_discord_file(pil_image: Image.Image, filename: str = "image.png"):
    """
    Converts a PIL Image object into a discord.File object.

    Args:
        pil_image (Image.Image): The PIL Image to convert.
        filename (str): The desired filename for the Discord attachment.
                        Must end with a supported image extension (e.g., .png, .jpeg).

    Returns:
        discord.File: A discord.File object ready to be sent.
    """
    try:
        image_bytes = io.BytesIO()
        # Save the PIL Image to the bytes buffer
        # Ensure the format matches the filename extension
        if filename.lower().endswith(".png"):
            pil_image.save(image_bytes, format='PNG')
        elif filename.lower().endswith((".jpg", ".jpeg")):
            pil_image.save(image_bytes, format='JPEG')
        elif filename.lower().endswith(".gif"):
            pil_image.save(image_bytes, format='GIF')
        else:
            logger.warning(f"Unsupported image format for filename '{filename}'. Defaulting to PNG.")
            pil_image.save(image_bytes, format='PNG')
            filename = os.path.splitext(filename)[0] + ".png" # Adjust filename if format changed

        image_bytes.seek(0) # Rewind the buffer to the beginning

        return discord.File(image_bytes, filename=filename)
    except Exception as e:
        logger.error(f"Failed to convert PIL Image to discord.File for '{filename}': {e}", exc_info=True)
        return None