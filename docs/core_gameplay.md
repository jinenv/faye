## Core Gameplay Loop
| Currency     | Role                       | How It’s Earned                  | How It’s Spent                       |
| ------------ | -------------------------- | -------------------------------- | ------------------------------------ |
| **Virelite** | Upgrade Esprits (leveling) | Daily, Explore, Dissolve, Quests | Upgrade cost per level (scaling)     |
| **Remna**  | Limit Break material       | Explore, Dissolve, Milestones    | Limit break cost (scales hard)       |
| **Faylen**   | Generic shop currency      | Explore, Daily                   | Shops, cosmetics, crafting, misc     |
| **Ethryl**   | Premium summon currency    | Rare rewards, Events, Milestones | `/summon premium`                    |
| **Fayrite**  | Standard summon currency   | Convert from shards              | `/summon standard`                   |
| **XP**       | Player level progression   | Explore, Achievements, Quests    | Unlocks esprit cap, prestige unlocks |

## Currency Ecosystem
| Currency     | Role                       | How It’s Earned                  | How It’s Spent                       |
| ------------ | -------------------------- | -------------------------------- | ------------------------------------ |
| **Virelite** | Upgrade Esprits (leveling) | Daily, Explore, Dissolve, Quests | Upgrade cost per level (scaling)     |
| **Remna**  | Limit Break material       | Explore, Dissolve, Milestones    | Limit break cost (scales hard)       |
| **Faylen**   | Generic shop currency      | Explore, Daily                   | Shops, cosmetics, crafting, misc     |
| **Ethryl**   | Premium summon currency    | Rare rewards, Events, Milestones | `/summon premium`                    |
| **Fayrite**  | Standard summon currency   | Convert from shards              | `/summon standard`                   |
| **XP**       | Player level progression   | Explore, Achievements, Quests    | Unlocks esprit cap, prestige unlocks |

## Progression Pacing
| System            | Gated By                     | Gating Logic                                 |
| ----------------- | ---------------------------- | -------------------------------------------- |
| **Esprit Level**  | Virelite                     | Linear XP cost curve per level               |
| **Limit Break**   | Remna, Virelite, Player XP | Must be at level cap + player level gate     |
| **Summon Access** | Fayrite shards / Ethryl      | Grinding or spending (fair summoning system) |
| **Player Level**  | XP                           | Earned slowly via core activities            |

## Incentive Layers
### Milestone Cog
| Milestone          | Reward                |
| ------------------ | --------------------- |
| 10 explores        | 5 Virelite, 1 Remna |
| 100 Virelite spent | 1 Fayrite shard       |
| First Limit Break  | 3 Ethryl              |
| Level 25 player    | Rare chest            |
| Own 10 Esprits     | Premium summon ticket |
etc...

### Achievement Cog
- Displays all unlockable achievements

- Marks completed ones

- Rewards are small but meaningful

- Optional: Tiers (e.g., 100 → 1,000 explores)

### Quest Cog
| Command               | Description                          |
| --------------------- | ------------------------------------ |
| `/quests`             | Lists active/completed quests        |
| `/quest activate [x]` | Lets player choose from pool (3 max) |
| `/quest complete`     | Checks status, gives reward          |

**Quests include:**
- Daily: Explore 5 times, earn 1k virelite

- Weekly: Win 10 battles, limit break 2 Esprits

- Seasonal: Collect 25 Esprits, max 1 Deity

### Fairness and Reward Loops
- Virelite flows regularly → daily dopamine

- Remna flows slowly → milestone pacing

- XP scales smartly → grindable, not grindy

- Milestones + achievements = surprise motivators

- Quests = intentional guidance for daily/weekly players