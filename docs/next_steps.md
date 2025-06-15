# Faye RPG Bot – Next Steps Checklist

## Summary of Accomplishments
- **Project Rebranding**
  - Completed rebrand from "Nyxa" to "Faye" (all user-facing text, internal code, and currency names).
- **Configuration Refactor**
  - Split `game_settings.json` into 7 smaller, logically-grouped config files (e.g., `economy_settings.json`, `summoning_settings.json`, `visuals.json`).
- **Database & Schema Management**
  - Database is up-to-date and managed by Alembic.
  - New fields added and migrations run (e.g., `locked`, `level_cap`).
- **Core Logic Hardening**
  - `/summon` command refactored for multi-summon view, locking, and stat checking.
  - Pity and drop rates are data-driven via config.
- **Game Balance Analysis**
  - Economy and progression deeply analyzed and tuned for engagement.

---

## TODO: Logic & Fact-Checking Phase

### 1. **Update Remaining Cogs to Use New Configs**
- [ ] **esprit_cog.py**
  - [ ] Update `__init__` to load `combat_settings.json` and `progression_settings.json`.
  - [ ] Refactor all commands (`/upgrade`, `/limitbreak`, `/dissolve`, etc.) to use new config, not legacy `game_settings`.
- [ ] **economy_cog.py**
  - [ ] Update to load `economy_settings.json` for daily rewards, crafting, etc.
- [ ] **onboarding_cog.py**
  - [ ] Update to load `economy_settings.json` (starter currencies) and `progression_settings.json` (onboarding rules).
- [ ] **Other Cogs (utility_cog, admin_cog, etc.)**
  - [ ] Review for any legacy `game_settings.json` references and refactor as needed.

---

### 2. **Implement Core Gameplay Cogs**
- [ ] **explore_cog.py**
  - [ ] Create `/explore` command.
    - [ ] Use `exploration_zones` from `activity_settings.json`.
    - [ ] Use `RNGManager` to grant rewards.
    - [ ] Add cooldown with `RateLimiter`.
- [ ] **trial_cog.py**
  - [ ] Create `/trial` command.
    - [ ] Use `player_trial_tiers` from `progression_settings.json`.
    - [ ] Gate player advancement accordingly.

---

### 3. **Advanced Caching (Redis)**
- [ ] **Current State**
  - [x] In-memory `CacheManager` working.
- [ ] **Upgrade Path**
  - [ ] When scaling to multi-process/server:
    - [ ] Swap out `CacheManager` dict for Redis backend.
    - [ ] Only update `get`/`set` in `src/utils/cache_manager.py`—no changes to cogs required.

---

## Foundation Complete — Now Build Gameplay!

All architectural refactoring is done. Next: **Finish cog refactors, launch new gameplay loops, prepare for scale.**
