import discord
from PIL import Image
from io import BytesIO
from src.utils.logger import Logger

# Initialize a logger for this module
log = Logger(__name__)

async def get_image_as_discord_file(pil_image: Image.Image, filename: str = "image.png") -> discord.File:
    """
    Converts a PIL Image object into a discord.File object.
    This operation is synchronous and should ideally be run in an executor if called
    from an async loop frequently.

    Args:
        pil_image (Image.Image): The Pillow Image object to convert.
        filename (str): The desired filename for the Discord file (e.g., "my_image.png").

    Returns:
        discord.File: A discord.File object ready to be sent, or None if an error occurs.
    """
    if not isinstance(pil_image, Image.Image):
        log.error(f"Provided image is not a PIL Image object: {type(pil_image)}. Expected Pillow Image.Image.")
        # For debugging, you might want to raise TypeError("Expected a PIL Image object.")
        return None

    buffer = BytesIO()
    try:
        # pil_image.save is a synchronous operation. If this causes blocking issues
        # for a busy bot, it might need to be run in a self.bot.loop.run_in_executor
        # from the calling async function (e.g., in the cog or view).
        pil_image.save(buffer, format="PNG") # Save the image to the in-memory buffer
        buffer.seek(0) # Rewind the buffer to the beginning
        log.debug(f"Successfully converted PIL Image to Discord File: {filename}")
        return discord.File(buffer, filename=filename)
    except Exception as e:
        log.error(f"Failed to convert PIL Image to Discord File {filename}: {e}", exc_info=True)
        return None