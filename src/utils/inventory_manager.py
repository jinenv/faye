import json
import os
from typing import List, Optional


class InventoryManager:
    """
    JSON‐backed inventory manager.

    - Stores per‐user: list of Esprit IDs they own.
    - Data file defaults to "data/inventory.json".
    """

    def __init__(self, data_file: str = "data/inventory.json"):
        self.data_file = data_file
        self._load_data()

    def _load_data(self):
        if os.path.isfile(self.data_file):
            try:
                with open(self.data_file, "r") as f:
                    self.data: dict = json.load(f)
            except json.JSONDecodeError:
                self.data = {}
        else:
            self.data = {}

    def _save_data(self):
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        with open(self.data_file, "w") as f:
            json.dump(self.data, f, indent=4)

    def _ensure_user(self, user_id: int):
        uid = str(user_id)
        if uid not in self.data:
            self.data[uid] = []

    def get_inventory(self, user_id: int) -> List[str]:
        self._ensure_user(user_id)
        return list(self.data[str(user_id)])

    def add_esprit(self, user_id: int, esprit_id: str) -> None:
        self._ensure_user(user_id)
        uid = str(user_id)
        self.data[uid].append(esprit_id)
        self._save_data()

    def remove_esprit(self, user_id: int, esprit_id: str) -> bool:
        self._ensure_user(user_id)
        uid = str(user_id)
        if esprit_id in self.data[uid]:
            self.data[uid].remove(esprit_id)
            self._save_data()
            return True
        return False
