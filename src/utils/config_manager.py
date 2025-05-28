import os
import json
import yaml
from src.utils.logger import Logger

log = Logger(__name__)

class ConfigManager:
    _cache = {}

    @classmethod
    def get_config(cls, category: str, filename: str) -> dict:
        cache_key = f"{category}/{filename}"
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        # --- FIX HERE: Go up one more directory level to reach PROJECT X root ---
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        # --- END FIX ---
        file_path = os.path.join(base_dir, 'data', category, filename)

        if not os.path.exists(file_path):
            log.error(f"Config file not found: {file_path}")
            return {}

        data = {}
        try:
            if filename.endswith('.json'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            elif filename.endswith('.yml') or filename.endswith('.yaml'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
            else:
                log.warning(f"Unsupported config file type: {filename}. Only .json and .yml/.yaml are supported.")
                return {}

            cls._cache[cache_key] = data
            log.info(f"Loaded config: {file_path}")
            return data

        except (json.JSONDecodeError, yaml.YAMLError) as e:
            log.error(f"Error decoding config file {file_path}: {e}")
        except Exception as e:
            log.error(f"An unexpected error occurred loading config {file_path}: {e}")
        return {}

    @classmethod
    def clear_cache(cls):
        cls._cache = {}
        log.info("ConfigManager cache cleared.")