# Comprehensive To-Do List

## Alembic Upgrade
- [ ] **Add `calculate_power` method to `UserEsprit` model** (0 days, Completed)
  - Implemented in `models.py` with rarity tiers: Common, Uncommon, Rare, Epic, Celestial, Supreme, Deity.
- [ ] **Add `calculate_stat` method to `UserEsprit` model** (0 days, Completed)
  - Implemented in `models.py`, but not fully utilized in `esprit_cog.py`.
- [ ] **Implement Aether as the premium currency** (High priority, 1-2 days)
  - Add `aether` field to `users` table via Alembic migration.
  - Create `aether_transactions` table (fields: `user_id`, `amount`, `transaction_type`, `timestamp`).
  - **Dependencies**: Needed for Summon Cog’s premium banner.
- [ ] **Implement `free_daily_summon` timer** (Medium priority, 0.5 days)
  - Add `last_free_summon` timestamp field to `users` table via Alembic migration.
  - Implement logic in Summon Cog to check 24-hour cooldown and update timestamp.
  - **Dependencies**: Requires Summon Cog implementation.

## Summon Cog
- [ ] **Pull banner logic from game settings for Premium (Aether-based) and Standard banners**
  - Define banner configurations (e.g., drop rates for Common to Deity tiers) in game settings.
  - Implement Premium banner using Aether and Standard banner using free resources.
  - **Dependencies**: Requires Aether implementation and game settings configuration.
- [ ] **Update summoning to summon only one Esprit at a time**
  - Modify summon logic to return a single Esprit per summon.
  - **Dependencies**: Part of Summon Cog implementation.
- [ ] **Cache summoned Esprit details immediately for `/esprit collection` display**
  - Use `EspritCache` (from `esprit_cog.py`) or `CacheManager` (from `utils`) to cache new Esprit after summoning.
  - Invalidate user collection cache post-summon.
  - **Dependencies**: Requires Summon Cog implementation.

## Esprit Cog
- [x] **/esprit collection: Implement view with filters**
  - Implemented with `EnhancedCollectionView`, supporting name, level, and rarity filters.
  - **Action**: Update rarity tiers (see below).
- [x] **/esprit details: Display detailed stats with growth potential**
  - Implemented with detailed embeds showing stats, combat stats, and max potential.
- [x] **/esprit upgrade: Support multi-level upgrades with rate limiting** (0 days, Completed)
  - Implemented with 1-10 level upgrades, `RateLimiter`, and Moonglow costs.
  - **Action**: Replace Moonglow with Aether.
- [x] **/esprit dissolve: Include confirmation dialog** (0 days, Completed)
  - Implemented as `/esprit bulk_dissolve` with `ConfirmationView` for multiple Esprits.
  - **Action**: Update rarity tiers (see below). Consider adding single dissolve if needed.
- [x] **/esprit compare: Enable side-by-side Esprit comparison** (0 days, Completed)
  - Implemented for 2-5 Esprits with power and stat comparisons.
- [ ] **/esprit equip: Quick equip to main slot** (Low priority, 0.5 days)
  - Implement command to set an Esprit as `active_esprit_id` (similar to `team_set`).
  - Invalidate user cache post-equip.
- [x] **/esprit search: Search Esprits by name** (0 days, Completed)
  - Implemented with name, class, and rarity search, plus level filters.
- [x] **/esprit team view: Analyze team with synergy metrics** (0 days, Completed)
  - Implemented with power calculations and placeholder synergy bonus (15%).
  - **Action**: Enhance synergy metrics (optional, see below).
- [x] **/esprit team set: Smart slot management for team setup** (0 days, Completed)
  - Implemented with slot assignments and swaps.
- [x] **/esprit team optimize: AI-powered team suggestions** (0 days, Completed, Bonus)
  - Implemented with basic class-based optimization (DPS, tank, healer).
- [ ] **Update rarity tiers in `esprit_cog.py`** (High priority, 0.5 days)
  - Update `EnhancedCollectionView`:
    - `rarity_order`: `{"Common": 0, "Uncommon": 1, "Rare": 2, "Epic": 3, "Celestial": 4, "Supreme": 5, "Deity": 6}`
    - `rarity_emoji`: `{"Common": "⚪", "Uncommon": "🟢", "Rare": "🔵", "Epic": "🟣", "Celestial": "🌌", "Supreme": "👑", "Deity": "✨"}`
    - `filter_select` options: Add Celestial, Supreme, Deity; remove Legendary, Mythic.
  - Update `BulkDissolveView`:
    - `valid_rarities`: `["Common", "Uncommon", "Rare", "Epic", "Celestial", "Supreme", "Deity"]`
  - Update `EspritGroup` helper methods:
    - `_get_rarity_color`: Map new tiers to colors (e.g., Celestial: `dark_blue`, Supreme: `gold`, Deity: `red`).
    - `_get_rarity_emoji`: Same as `rarity_emoji` above.
  - **Dependencies**: Should be done before testing to ensure consistency.
- [ ] **Refactor stat calculations in `esprit_cog.py`** (Medium priority, 0.5 days)
  - Replace inline stat calculations (e.g., in `details`, `compare`) with `user_esprit.calculate_stat()` calls.
  - Example: In `details`, change `int(ed.base_hp * level_multiplier)` to `user_esprit.calculate_stat("hp")`.
  - **Dependencies**: Requires `calculate_stat` in `models.py`.
- [ ] **Enhance synergy metrics in `team_view`** (Optional, Low priority, 1-2 days)
  - Replace `_calculate_synergy_bonus` placeholder with logic based on class, element, or ability matchups (e.g., +5% for matching elements).
  - Update `team_optimize` to consider synergy in suggestions.

## Additional Tasks
- [ ] **Configure game settings** (High priority, 0.5 days)
  - Define drop rates for summon banners (e.g., Deity: 0.5%, Celestial: 2%).
  - Set Aether costs for premium summons and upgrades.
  - Update `dissolve_rewards` in `esprit_cog.py` for new rarity tiers.
  - **Dependencies**: Needed for Summon Cog and Aether integration.
- [ ] **Testing** (Medium priority, 1-2 days)
  - Write unit tests for:
    - `calculate_power` and `calculate_stat` in `models.py`.
    - `EspritCache` methods in `esprit_cog.py`.
    - Command logic (e.g., `/esprit upgrade`, `/esprit compare`).
  - Write integration tests for:
    - Summoning with Aether deductions.
    - Upgrades with cache invalidation.
    - Team setup and power calculations.
  - **Dependencies**: Complete after core implementation.

## Notes
- **Priority Order**:
  1. Rarity tier updates (ensures consistency).
  2. Aether integration and game settings (unblocks Summon Cog).
  3. Summon Cog (core gameplay feature).
  4. `free_daily_summon`, `/esprit equip`, refactoring (smaller tasks).
  5. Testing (ensures stability).
  6. Synergy enhancement (optional polish).
- **Dependencies**:
  - Ensure `models.py` with `calculate_power` and `calculate_stat` is added before testing `esprit_cog.py`.
  - Complete Aether migrations before updating `/esprit upgrade` or Summon Cog.
- **Testing Tips**:
  - Mock database sessions for unit tests using `unittest.mock`.
  - Use `pytest` with `pytest-asyncio` for async tests.
- **Game Settings**:
  - Store in a JSON file or database table, accessible via `bot.config_manager`.
  - Example: `{"banners": {"premium": {"Deity": 0.005, ...}}, "upgrade_costs": {...}}`.
- **Aether Transactions**:
  - Log all Aether changes (e.g., summons, upgrades) to `aether_transactions` for auditing.
  - Use transactions to ensure consistency (e.g., rollback on summon failure).
