# src/database/data_loader.py
import json
import asyncio
from pathlib import Path
from sqlmodel import select
from src.database.db import get_session
from src.database.models import EspritData
from src.utils.logger import get_logger

log = get_logger(__name__)

class EspritDataLoader:
    def __init__(self, json_path: str = "data/config/esprits.json"):
        self.json_path = Path(json_path)
        
    async def load_esprits(self, force_reload: bool = False):
        """Load Esprit data from JSON file into database.
        
        Args:
            force_reload: If True, will update existing entries. If False, only adds new ones.
            
        Returns:
            Number of Esprits loaded/updated
        """
        if not self.json_path.exists():
            log.error(f"Esprit data file not found: {self.json_path}")
            raise FileNotFoundError(f"Could not find {self.json_path}")
            
        with open(self.json_path, 'r', encoding='utf-8') as f:
            esprits_data = json.load(f)
            
        loaded_count = 0
        async with get_session() as session:
            for esprit_id, data in esprits_data.items():
                # Check if esprit already exists
                result = await session.execute(
                    select(EspritData).where(EspritData.esprit_id == esprit_id)
                )
                existing = result.scalar_one_or_none()
                
                if existing and not force_reload:
                    continue  # Skip if already exists and not forcing reload
                    
                if existing and force_reload:
                    # Update existing entry
                    for key, value in data.items():
                        if hasattr(existing, key):
                            setattr(existing, key, value)
                    log.info(f"Updated Esprit: {esprit_id}")
                else:
                    # Create new entry
                    esprit = EspritData(
                        esprit_id=esprit_id,
                        name=data.get('name', 'Unknown'),
                        description=data.get('description', ''),
                        rarity=data.get('rarity', 'Common'),
                        class_name=data.get('class_name', 'Unknown'),
                        visual_asset_path=data.get('visual_asset_path', ''),
                        base_hp=data.get('base_hp', 100),
                        base_attack=data.get('base_attack', 10),
                        base_defense=data.get('base_defense', 10),
                        base_speed=data.get('base_speed', 10),
                        base_magic_resist=data.get('base_magic_resist', 0),
                        base_crit_rate=data.get('base_crit_rate', 0.0),
                        base_block_rate=data.get('base_block_rate', 0.0),
                        base_dodge_chance=data.get('base_dodge_chance', 0.0),
                        base_mana_regen=data.get('base_mana_regen', 0),
                        base_mana=data.get('base_mana', 0)
                    )
                    session.add(esprit)
                    log.info(f"Added new Esprit: {esprit_id}")
                    
                loaded_count += 1
                
                # Commit in batches for performance
                if loaded_count % 50 == 0:
                    await session.commit()
                    log.info(f"Committed batch: {loaded_count} Esprits processed")
                    
            await session.commit()
            
        log.info(f"Esprit data loading complete: {loaded_count} Esprits loaded/updated")
        return loaded_count
        
    async def verify_data_integrity(self):
        """Verify all Esprits in JSON exist in database.
        
        Returns:
            List of missing Esprit IDs
        """
        if not self.json_path.exists():
            return []
            
        with open(self.json_path, 'r', encoding='utf-8') as f:
            esprits_data = json.load(f)
            
        missing = []
        async with get_session() as session:
            for esprit_id in esprits_data.keys():
                result = await session.execute(
                    select(EspritData).where(EspritData.esprit_id == esprit_id)
                )
                if not result.scalar_one_or_none():
                    missing.append(esprit_id)
                    
        if missing:
            log.warning(f"Missing Esprits in database: {missing}")
        else:
            log.info("All Esprits verified in database")
            
        return missing

# Standalone script functionality
async def main():
    """Run the loader as a standalone script."""
    loader = EspritDataLoader()
    try:
        count = await loader.load_esprits(force_reload=False)
        print(f"Successfully loaded {count} Esprits")
        missing = await loader.verify_data_integrity()
        if missing:
            print(f"Warning: {len(missing)} Esprits are missing from database")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())