import discord
from PIL import Image
from io import BytesIO
from src.utils.logger import Logger

# Initialize a logger for this module
log = Logger(__name__)

async def get_image_as_discord_file(pil_image: Image.Image, filename: str = "image.png") -> discord.File:
    """
    Converts a PIL Image object into a discord.File object.

    Args:
        pil_image (Image.Image): The Pillow Image object to convert.
        filename (str): The desired filename for the Discord file (e.g., "my_image.png").

    Returns:
        discord.File: A discord.File object ready to be sent.
    """
    if not isinstance(pil_image, Image.Image):
        log.error(f"Provided image is not a PIL Image object: {type(pil_image)}")
        raise TypeError("Expected a PIL Image object.")

    buffer = BytesIO()
    try:
        pil_image.save(buffer, format="PNG") # Save the image to the in-memory buffer
        buffer.seek(0) # Rewind the buffer to the beginning
        log.debug(f"Successfully converted PIL Image to Discord File: {filename}")
        return discord.File(buffer, filename=filename)
    except Exception as e:
        log.error(f"Failed to convert PIL Image to Discord File {filename}: {e}")
        return None