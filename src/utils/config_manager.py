# src/utils/config_manager.py
import json
from pathlib import Path
from .logger import get_logger

logger = get_logger(__name__)

def load_all_configs(base_path: str = 'data/config') -> dict:
    """
    Loads all .json files from the specified directory into a single dictionary.
    The filename (without extension) is used as the key.
    """
    config_dir = Path(base_path)
    all_configs = {}
    
    if not config_dir.is_dir():
        logger.error(f"Configuration directory not found at '{config_dir}'")
        return {}

    for path in config_dir.glob("*.json"):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                # Use the filename (e.g., "economy_settings") as the key
                all_configs[path.stem] = json.load(f)
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON from '{path}'")
        except Exception as e:
            logger.error(f"Failed to load config file '{path}': {e}")
            
    logger.info(f"Successfully loaded {len(all_configs)} configuration files.")
    return all_configs