# Comprehensive To-Do List – Concurrency-Safe (Sync Point 2025-06-12)

Legend  
✔ = complete △ = partial ⬜ = not started ✱ = concurrency risk, audit required

────────────────────────────────────────────────────────────────────────────
Alembic / Model Work
────────────────────────────────────────────────────────────────────────────
✔ `calculate_power` method on `UserEsprit`
✔ `calculate_stat` method on `UserEsprit` (✱: confirm stat-updating ops always hit latest model instance)
✔ Aether column exists (`users.aether`) — daily + premium banner use it
⬜ `aether_transactions` audit table (✱: log every aether change; lock row for write on insert)
✔ `last_free_summon` timestamp — Summon Cog logic implemented (✱: check for double-claim on fast repeat/click)

────────────────────────────────────────────────────────────────────────────
Summon Cog
────────────────────────────────────────────────────────────────────────────
✔ Banner configs pulled from `game_settings.json` (standard = Azurites, premium = Aether)
✔ Summon returns one Esprit per call
✔ Cache invalidation after summon (collection reflects instantly)
✔ Pity system reworked (config-driven increments, % bar)
✱: Ensure all /summon actions are atomic—DB transaction per summon, no double-draw if user spams.
✱: Check for race conditions on pity counters—use SELECT FOR UPDATE if needed.

────────────────────────────────────────────────────────────────────────────
Esprit Cog
────────────────────────────────────────────────────────────────────────────
✔ `/esprit collection` view + filters
✔ `/esprit details`, `/compare`, `/dissolve`, `/upgrade`
✔ TeamSlot dropdown for `/esprit team set` + optimize/view
⬜ `/esprit equip` (low priority)
⬜ Stat refactor – replace inline math with `calculate_stat()` throughout (✱: test for old cache/stale stat)
⬜ Synergy metrics (optional)
✱: Any esprit add/remove/upgrade/dissolve must invalidate profile & collection caches immediately, for all concurrent viewers.

────────────────────────────────────────────────────────────────────────────
Game Settings / Economy
────────────────────────────────────────────────────────────────────────────
✔ Five-pillar currency in config
✔ Drop rates + pity increments in both banners
△ `dissolve_rewards` covers new rarities (✱: reward calculation must be non-racy, audit for double-claim)

────────────────────────────────────────────────────────────────────────────
Concurrency-Critical Items
────────────────────────────────────────────────────────────────────────────
1. **DB Transaction Safety:**
    - All commands that *write* user/currency/esprit state must wrap DB calls in a transaction block.
    - Use session-level locks or DB-level row/field locks where supported (`SELECT ... FOR UPDATE` if possible; fallback to app logic in SQLite).
2. **Atomic Operations:**
    - Prevent double-claims: `/daily`, `/summon`, `/upgrade`, `/dissolve`, etc., should be atomic (no two can succeed simultaneously for one user).
    - Consider a *short-lived* in-memory mutex or redis lock per user ID if rapid-fire commands are an issue.
3. **Cache Consistency:**
    - On any esprit/currency change, *all relevant caches* must be purged or updated.
    - Never serve user profile or esprit data from stale cache after DB mutation.
4. **Aether Transactions Table:**
    - Write every aether deduction/add as an audit row inside the same transaction as the balance update.
    - Audit log should be append-only and reflect all mutations, with a timestamp and reason.
5. **Unit & Integration Tests:**
    - All tests should run commands in parallel (async) to simulate multi-user load and test race conditions.

────────────────────────────────────────────────────────────────────────────
Testing Checklist (Concurrency-Specific)
────────────────────────────────────────────────────────────────────────────
☐ *Simultaneous* `/summon` and `/daily` calls for one user: only one should succeed per cooldown/criteria.
☐ Multi-user `/summon` does not bleed state across users (no global race).
☐ Repeated esprit upgrades or dissolves never cause double-spend or negative balances.
☐ After an esprit is dissolved/upgraded, user profile/collection reflects change instantly (no stale data).

────────────────────────────────────────────────────────────────────────────
Notes & Dependencies
────────────────────────────────────────────────────────────────────────────
- DB schema changes must consider concurrent migrations (never drop+recreate a live table without a lock/migration window).
- All config reloads are thread-safe/atomic (prefer reloading into a new dict, then swap references).
- For SQLite: true row-level locking is limited. If you hit race bugs, consider switching to Postgres for production.

# Summary:
# For each “modifies user/account” command: **one DB transaction, one cache flush, no double-exec.**
# Log/audit every currency change in the same transaction.
# Use explicit testing for concurrency bugs (not just single-user flows).
# If on SQLite, know its limitations—sometimes extra app-layer mutexes are needed.
 
