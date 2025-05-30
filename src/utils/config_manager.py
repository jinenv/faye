# src/utils/config_manager.py
import json
import yaml
import os
from functools import lru_cache

from src.utils.logger import get_logger # Use get_logger for consistency

logger = get_logger(__name__)

class ConfigManager:
    """
    Manages loading and caching of configuration files (JSON, YAML).
    """
    def __init__(self, config_base_path="data/config"):
        self.config_base_path = config_base_path
        self._config_cache = {} # Internal cache for loaded configs

    @lru_cache(maxsize=32) # Cache up to 32 different config files
    def get_config(self, config_name: str):
        """
        Loads a configuration file by name, preferring YAML over JSON, and caches it.
        Example: get_config('game_settings') will look for game_settings.yaml or game_settings.json.
        """
        if config_name in self._config_cache:
            return self._config_cache[config_name]

        file_path_yaml = os.path.join(self.config_base_path, f"{config_name}.yaml")
        file_path_json = os.path.join(self.config_base_path, f"{config_name}.json")

        config_data = None
        file_found = None

        if os.path.exists(file_path_yaml):
            try:
                with open(file_path_yaml, 'r', encoding='utf-8') as f:
                    config_data = yaml.safe_load(f)
                file_found = file_path_yaml
            except Exception as e:
                logger.error(f"Error loading YAML config '{file_path_yaml}': {e}", exc_info=True)
        elif os.path.exists(file_path_json):
            try:
                with open(file_path_json, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                file_found = file_path_json
            except Exception as e:
                logger.error(f"Error loading JSON config '{file_path_json}': {e}", exc_info=True)
        else:
            logger.warning(f"Config file '{config_name}.yaml' or '{config_name}.json' not found in '{self.config_base_path}'")

        if config_data is None:
            config_data = {} # Return an empty dict if config not found or error occurred

        self._config_cache[config_name] = config_data
        if file_found:
            logger.info(f"Loaded config: {file_found}")
        return config_data

    # You could add methods here to reload configs, or validate them.