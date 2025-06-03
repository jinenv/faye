# src/utils/config_manager.py
import json
import yaml
import os  # Ensure os is imported for os.getcwd()
from pathlib import Path
from .logger import get_logger

# Initialize logger for this module
logger = get_logger(__name__)

class ConfigManager:
    def __init__(self, base_path='.'):
        self.base_path = Path(base_path).resolve() # Resolve base_path to an absolute path on init
        self.cache = {}
        # Log the absolute base path this ConfigManager instance will use
        logger.info(f"ConfigManager initialized. Absolute base_path: '{self.base_path}'")

    def _load_file(self, file_path: Path, file_type: str):
        """
        Loads a file's content. file_type should be 'json' or 'yaml'.
        """
        try:
            # Ensure file_path is absolute for clarity in logs and operations
            abs_file_path = file_path.resolve()
            logger.debug(f"ConfigManager._load_file: Attempting to open '{abs_file_path}' as {file_type}")
            with open(abs_file_path, 'r', encoding='utf-8') as f:
                if file_type == 'json':
                    return json.load(f)
                elif file_type == 'yaml':
                    return yaml.safe_load(f) # Use safe_load for YAML
                else:
                    logger.warning(f"ConfigManager._load_file: Unsupported file type: {file_type} for {abs_file_path}")
                    return None
        except FileNotFoundError:
            # This should ideally not be hit if exists() is checked prior to calling _load_file,
            # but it's a good fallback.
            logger.error(f"ConfigManager._load_file: File not found at '{abs_file_path}'")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"ConfigManager._load_file: JSON decode error in '{abs_file_path}': {e}")
            return None
        except yaml.YAMLError as e:
            logger.error(f"ConfigManager._load_file: YAML decode error in '{abs_file_path}': {e}")
            return None
        except Exception as e:
            logger.error(f"ConfigManager._load_file: Unexpected error loading file '{abs_file_path}': {e}", exc_info=True)
            return None

    def get_config(self, relative_path: str):
        """
        Loads a configuration file (JSON or YAML) based on the provided relative path.
        The method first looks for a .yaml file, then for a .json file if .yaml is not found,
        by appending the extensions to the given relative_path.
        """
        # --- DETAILED LOGGING AT THE START ---
        current_cwd = os.getcwd()
        logger.info(f"ConfigManager.get_config: CALLED with relative_path: '{relative_path}'")
        logger.info(f"ConfigManager.get_config: Current Working Directory (CWD): '{current_cwd}'")
        logger.info(f"ConfigManager.get_config: Instance base_path: '{self.base_path}'")
        # --- END DETAILED LOGGING ---

        if not isinstance(relative_path, str):
            logger.error(f"ConfigManager.get_config: relative_path was not a string: {type(relative_path)} (value: {relative_path})")
            # Optionally, raise TypeError or return None based on desired strictness
            # For now, attempting to convert to Path might still work if it's Path-like, but log clearly.
            # raise TypeError("relative_path must be a string")
            return None # Safer to return None if type is wrong

        path_obj = Path(relative_path) # e.g., Path('data/config/esprits')

        # Construct full paths and check existence
        yaml_path_to_check = (self.base_path / f"{path_obj}.yaml").resolve()
        json_path_to_check = (self.base_path / f"{path_obj}.json").resolve()

        # --- MORE DETAILED LOGGING for path construction and existence check ---
        logger.info(f"ConfigManager.get_config: Checking for YAML at absolute path: '{yaml_path_to_check}'")
        yaml_exists = yaml_path_to_check.exists()
        logger.info(f"ConfigManager.get_config: YAML path exists: {yaml_exists}")

        logger.info(f"ConfigManager.get_config: Checking for JSON at absolute path: '{json_path_to_check}'")
        json_exists = json_path_to_check.exists()
        logger.info(f"ConfigManager.get_config: JSON path exists: {json_exists}")
        # --- END MORE DETAILED LOGGING ---

        # Try loading as YAML first
        if yaml_exists:
            full_path_str = str(yaml_path_to_check) # Use resolved absolute path for cache key
            if full_path_str in self.cache:
                logger.debug(f"ConfigManager.get_config: Returning cached content for YAML: '{full_path_str}'")
                return self.cache[full_path_str]
            
            loaded_content = self._load_file(yaml_path_to_check, 'yaml')
            if loaded_content is not None:
                self.cache[full_path_str] = loaded_content
                logger.info(f"ConfigManager.get_config: Successfully loaded YAML config: '{yaml_path_to_check}'")
                return loaded_content
            # If loaded_content is None, it means _load_file failed and logged it. Fall through to try JSON or final warning.

        # If YAML not found or failed, try loading as JSON
        if json_exists:
            full_path_str = str(json_path_to_check) # Use resolved absolute path for cache key
            if full_path_str in self.cache:
                logger.debug(f"ConfigManager.get_config: Returning cached content for JSON: '{full_path_str}'")
                return self.cache[full_path_str]

            loaded_content = self._load_file(json_path_to_check, 'json')
            if loaded_content is not None:
                self.cache[full_path_str] = loaded_content
                logger.info(f"ConfigManager.get_config: Successfully loaded JSON config: '{json_path_to_check}'")
                return loaded_content
            # If loaded_content is None, it means _load_file failed and logged it. Fall through to final warning.
        
        # If neither YAML nor JSON file was found and loaded successfully
        logger.warning(
            f"ConfigManager.get_config: Config file for base '{relative_path}' NOT FOUND. "
            f"Checked for YAML at: '{yaml_path_to_check}' (Exists: {yaml_exists}). "
            f"Checked for JSON at: '{json_path_to_check}' (Exists: {json_exists})."
        )
        return None