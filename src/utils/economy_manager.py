import json
import os
from datetime import datetime, timedelta
from typing import Optional


class EconomyManager:
    """
    JSON‐backed economy manager that tracks:
      • balance (gold)
      • last_daily timestamp
      • dust (currency earned from discards)
    """

    def __init__(self, data_file: str = "data/economy.json"):
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
            self.data[uid] = {
                "balance": 0,
                "last_daily": None,
                "dust": 0
            }

    def get_balance(self, user_id: int) -> int:
        self._ensure_user(user_id)
        return int(self.data[str(user_id)].get("balance", 0))

    def add_balance(self, user_id: int, amount: int) -> None:
        self._ensure_user(user_id)
        uid = str(user_id)
        self.data[uid]["balance"] = self.get_balance(user_id) + amount
        self._save_data()

    def deduct_balance(self, user_id: int, amount: int) -> bool:
        self._ensure_user(user_id)
        uid = str(user_id)
        current = self.get_balance(user_id)
        if current >= amount:
            self.data[uid]["balance"] = current - amount
            self._save_data()
            return True
        return False

    def get_dust(self, user_id: int) -> int:
        self._ensure_user(user_id)
        return int(self.data[str(user_id)].get("dust", 0))

    def add_dust(self, user_id: int, amount: int) -> None:
        self._ensure_user(user_id)
        uid = str(user_id)
        self.data[uid]["dust"] = self.get_dust(user_id) + amount
        self._save_data()

    def can_claim_daily(self, user_id: int) -> bool:
        self._ensure_user(user_id)
        last_daily_str = self.data[str(user_id)].get("last_daily")
        if not last_daily_str:
            return True
        try:
            last_dt = datetime.fromisoformat(last_daily_str)
        except Exception:
            return True
        return datetime.utcnow() - last_dt >= timedelta(hours=24)

    def claim_daily(self, user_id: int, amount: int) -> bool:
        if self.can_claim_daily(user_id):
            uid = str(user_id)
            self.data[uid]["last_daily"] = datetime.utcnow().isoformat()
            self.data[uid]["balance"] = self.get_balance(user_id) + amount
            self._save_data()
            return True
        return False

    def get_time_until_next_daily(self, user_id: int) -> Optional[timedelta]:
        self._ensure_user(user_id)
        last_daily_str = self.data[str(user_id)].get("last_daily")
        if not last_daily_str:
            return timedelta(0)
        try:
            last_dt = datetime.fromisoformat(last_daily_str)
        except Exception:
            return timedelta(0)
        next_dt = last_dt + timedelta(hours=24)
        remaining = next_dt - datetime.utcnow()
        return remaining if remaining > timedelta(0) else timedelta(0)



