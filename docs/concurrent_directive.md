# Nyxa / Faye – Unified Directive & State Architecture  
**Document Version:** 2.2  **Last Updated:** 2025-06-12  

This is the authoritative spec for every AI or human contributor.  
_If new work contradicts this file, update the file first._

────────────────────────────────────────────────────────────────────────────  
1 • Foundational Accomplishments   ✔ = done  
────────────────────────────────────────────────────────────────────────────  
• Core Architecture & DB  
  ✔ Python 3.12 · discord.py 2.3.2 · SQLModel base  
  ✔ Alembic migrations (manual-vetted)  
  ✔ Data-model refactor (User, UserEsprit, EspritData)  
  ✔ Startup script auto-installs deps + runs migrations  

• Gameplay & Economy  
  ✔ **Five-pillar currency**: Nyxies, Moonglow, Azurite Shards, Azurites, **Aether (premium)**  
  ✔ `/craft` converts shards → Azurites  
  ✔ `/start`, `/daily`, `/inventory`, `/summon`, basic `/explore` live  
  ✔ `/esprit upgrade` spends Moonglow; level gated by player level  
  ✔ **Sigil** replaces “Combat Power” everywhere  

• Summoning System v2 (2025-06-12)  
  ✔ Config-driven pity (`rarity_pity_increment`) – higher rarity adds points, bar shows %  
  ✔ `standard` banner costs Azurites; `premium` banner costs **Aether**  
  ✔ Guarantee at 50 points forces Epic+, then resets  
  ✔ Embed footer shows UID; author line removed, spacing polished  

• Esprit Management  
  ✔ Collection / details / compare / bulk-&-single dissolve  
  ✔ Team group: `/esprit team view|set|optimize` with dropdown enum `TeamSlot`  

• Backend & Utils  
  ✔ RateLimiter on spam-able commands  
  ✔ CacheManager invalidation after summons/upgrades/dissolves  
  ✔ Pillow image generation in executor thread pool  

• Schema Tweaks (migrated)  
  ✔ `EspritData.base_speed` & `base_mana_regen` → float (warnings fixed)  

────────────────────────────────────────────────────────────────────────────  
2 • Architectural Guarantees  (never break)  
────────────────────────────────────────────────────────────────────────────  
G1 Modularity – feature Cogs, shared Utils, Views in `src/views/`  
G2 Single-location logic – calculations live on model classes  
G3 Config-driven – tunables in `data/config/*`; load via ConfigManager  
G4 One AsyncSession per command; pass to helpers  
G5 RateLimiter at start of spammable commands  
G6 File header `logger = get_logger(__name__)`  
G7 Alembic discipline – autogen → manual review → upgrade  
G8 Heavy CPU work runs in executor; event loop stays responsive  

────────────────────────────────────────────────────────────────────────────  
3 • Mandatory Config Keys (game_settings.json excerpt)  
────────────────────────────────────────────────────────────────────────────  
"summoning": {  
  "pity_system_guarantee_after": 100,  
  "rarity_pity_increment": { "Common":1,"Uncommon":2,"Rare":3,"Epic":6,"Celestial":8,"Supreme":10,"Deity":12 },  
  "banners": {  
    "standard": { "cost_single": 1 },        // cost in Azurites  
    "premium":  { "cost_single": 1 }         // cost in Aether  
  }  
}  

────────────────────────────────────────────────────────────────────────────  
4 • SummonCog Algorithm (spec)  
────────────────────────────────────────────────────────────────────────────  
1 Roll rarity by banner weights  
2 new_pity = old + rarity_pity_increment[rarity]  
3 If new_pity ≥ guarantee_after → force Epic+, set new_pity = 0  
4 Deduct Azurites (standard) or **Aether** (premium)  
5 Embed:  
     <emoji> **<name>**  
     **<rarity>** | Sigil: 💥 <power>  
       
     [█████─────] 42 %  
   Footer: UID  

────────────────────────────────────────────────────────────────────────────  
5 • Team Management UX (enum dropdown)  
────────────────────────────────────────────────────────────────────────────  
from enum import IntEnum  
class TeamSlot(IntEnum):  
    leader = 1  
    support1 = 2  
    support2 = 3  

`team_set` uses `slot: TeamSlot`; internal logic uses `slot.value`.  

────────────────────────────────────────────────────────────────────────────  
6 • Pre-Merge Checklist  
────────────────────────────────────────────────────────────────────────────  
☑ Guarantees G1-G8 upheld  
☑ ruff / flake8 passes  
☑ Tests updated  
☑ Config keys present & documented  
☑ Alembic revision vetted (no stray FK resurrection)  
☑ Bot boots; slash-command sync clean  

_Follow “the Nyxa way.” If new work conflicts, update this file first._
