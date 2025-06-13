# Comprehensive To-Do List (sync point 2025-06-12)

Legend  
✔ = completed & merged △ = partially done ⬜ = not started

────────────────────────────────────────────────────────────────────────────
Alembic / Model Work
────────────────────────────────────────────────────────────────────────────
✔ **`calculate_power` method on `UserEsprit`**  
✔ **`calculate_stat` method on `UserEsprit`** (in models; still needs full cog adoption → see below)  
✔ **Aether column already exists** (`users.aether`) — daily rewards + premium banner use it  
⬜ **`aether_transactions` audit table**  
✔ **`last_free_summon` timestamp** (`users.last_daily_summon`) – logic implemented in Summon Cog

────────────────────────────────────────────────────────────────────────────
Summon Cog
────────────────────────────────────────────────────────────────────────────
✔ Banner configs pulled from `game_settings.json` (standard = Azurites, premium = Aether)  
✔ Summon returns **one** Esprit per call  
✔ Cache invalidation after summon (collection reflects instantly)  
✔ Pity system reworked (config‐driven increments, % bar)

────────────────────────────────────────────────────────────────────────────
Esprit Cog
────────────────────────────────────────────────────────────────────────────
✔ `/esprit collection` view + filters (rarity tiers updated: Celestial, Supreme, Deity)  
✔ `/esprit details`, `/compare`, `/dissolve`, `/upgrade` (Moonglow)  
✔ Dropdown **`TeamSlot`** for `/esprit team set` + `optimize` & `view`  
⬜ `/esprit equip` (quick leader set — low priority)  
⬜ **Stat refactor** – replace inline math with `calculate_stat()` throughout cog  
⬜ **Synergy metrics** – improve placeholder logic (optional polish)

────────────────────────────────────────────────────────────────────────────
Game Settings / Economy
────────────────────────────────────────────────────────────────────────────
✔ Five-pillar currency in config (Nyxies, Moonglow, Azurite Shards, Azurites, **Aether**)  
✔ Drop rates + pity increments present for both banners  
△ `dissolve_rewards` covers new rarities (verify Supreme/Deity values)  

────────────────────────────────────────────────────────────────────────────
Remaining High-Priority Items
────────────────────────────────────────────────────────────────────────────
1. **Create `aether_transactions` table** + logging utility (summons, future premium sinks)  
2. **Adopt `calculate_stat()` in Esprit Cog** (details, compare, team view).  
3. **Unit / integration tests**  
   • Model methods (`calculate_power`, `calculate_stat`)  
   • Summon flow (Aether deduction, pity % reset)  
   • Cache invalidation after upgrade / dissolve / summon  
4. **Optional**: `/esprit equip` shorthand command.  
5. **Optional**: Replace placeholder synergy bonus with element / class scoring.  

────────────────────────────────────────────────────────────────────────────
Testing Checklist (once features above land)
────────────────────────────────────────────────────────────────────────────
☐ Mock DB sessions with `pytest-asyncio` + `unittest.mock`.  
☐ CI target: coverage ≥ 80 %.  
☐ Ensure Alembic autogenerate diff is **empty** after migrations.  

────────────────────────────────────────────────────────────────────────────
Notes & Dependencies
────────────────────────────────────────────────────────────────────────────
- Any new schema field → SQLModel update + Alembic revision (manual review!).  
- All tunables continue to live in `data/config/*.json`; no magic numbers in code.  
- `dissolve_rewards`, banner drop rates, aether costs stay in config for live balance tweaks.  
