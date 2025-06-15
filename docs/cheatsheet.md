# Faye RPG: Deep System Calculations, Projections, and Min/Max Paths

---

## 1. Player Progression: XP, Level, Cap, and Time To Max

### **Level Curve Recap**
- XP to next: `100 * (level ^ 1.5)`
- Cumulative to 80: `965,506 XP`

### **Time to Max (Daily XP Only)**
- Assume only **explore** daily, +25 XP per run, unlimited runs.
- Daily claim grants **no direct XP**.
- To reach L80 from scratch:  
  `965,506 XP / (N * 25 XP per explore)` = **Number of actions required**  
  - If player does 20 explores/day: `965,506 / (20*25) ≈ 1,931 days`
  - If player grinds 100/day: `965,506 / 2,500 ≈ 386 days`

---

## 2. Esprit Progression: Upgrades, Limit Breaks, Total Cost

### **Upgrade Path**
- Level up cost: `15 + (level * 8)` (Virelite)
- Cumulative to 200: `162,800 Virelite` per Esprit

### **Limit Breaks: Total Cost/Boost**
- Max level: See rarity cap (Deity: 200)
- Each break:
  - Increases stat by +10%
  - Multiplies cost by 1.5x per break
- Total Remna for 5 breaks at Deity/200:  
  - `cost = base * rarity_mult * level_mult * (1.5 ^ N)`
  - See prior table for full progression

---

## 3. Summoning: Math, Pity, Probability, and Expected Pulls

### **Banner Pulls: Probability Distribution**
- Standard banner, chance for Deity: `0.05%` per pull
- **Expected pulls for 1 Deity:**  
  - `1 / 0.0005 = 2,000 pulls` (if no pity)

### **Supreme Pity:**
- After 100 pulls, get a guaranteed Supreme (if no Supreme/Deity)
- If always unlucky, Supreme every 100 pulls (pity reset if Supreme/Deity pulled)
- **Expected number of pulls for Supreme:**
  - If unlucky: 100
  - If normal odds: `1 / 0.005 = 200 pulls` (but pity halves this worst-case)

### **Daily Summon Limit:**  
- Max Fayrite per day from daily: 1
- Max pulls from pure daily income/month: 30

---

## 4. Crafting: Fayrite Output Projection

- 10 shards = 1 fayrite
- Daily: 10 shards = 1 fayrite
- Monthly: 300 shards = 30 fayrite

---

## 5. Dissolve: Long-Term Value

- Dissolve Epic: 750 Virelite, 75 Remna
- Dissolve Deity: 12,500 Virelite, 1,250 Remna

### **Meta:**
- **Is it ever optimal to dissolve high-rarity units?**  
  No, unless inventory full and cap exceeded, or for event/resource loop.

---

## 6. Limit Break/Upgrade Optimal Path

- **Optimal:**
  1. Max level Esprit
  2. Limit break (at cost spike per break)
  3. Upgrade to new cap
  4. Repeat
- **Material bottleneck:** Remna (esp. for high rarities), then Virelite

---

## 7. Esprit Stat & Power Calculation: Concrete Example

```python
# Example: Epic, level 125, 2 limit breaks, base HP 1000, Attack 500, Defense 500
level = 125
breaks = 2
base_stats = {'hp': 1000, 'attack': 500, 'defense': 500}
sigil_weights = {'hp': 0.25, 'attack': 2.5, 'defense': 2.5}
rarity_mult = 1.4  # Epic

level_mult = 1 + (level - 1) * 0.05  # = 1 + 124*0.05 = 7.2
break_mult = 1.1 ** breaks  # = 1.21

final_stats = {}
for stat, base in base_stats.items():
    final_stats[stat] = base * level_mult * break_mult

# Stat values:
# HP: 1000 * 7.2 * 1.21 = 8,712
# Attack: 500 * 7.2 * 1.21 = 4,356
# Defense: 500 * 7.2 * 1.21 = 4,356

# Power:
power = sum(final_stats[stat] * sigil_weights[stat] for stat in final_stats) * rarity_mult
# (HP*0.25 + ATK*2.5 + DEF*2.5) * 1.4 = (2178 + 10890 + 10890) * 1.4 = (23958) * 1.4 = 33,341
```

---

## 8. Eventual Max: All-in Scenarios

### **Max Player**
- Level 80, all Esprit slots unlocked (200)
- If daily play only: will take **several years** due to grind

### **Max Esprit**
- Deity, level 200, 10 limit breaks
- Stat: `base * (1 + (199 * .05)) * (1.1^10)` = base * 10.95 * 2.5937 = base * 28.43

---

## 9. Activity/Income Efficiency

| Source           | Daily Virelite | Daily Remna | Daily Fayrite | Monthly Virelite | Monthly Remna | Monthly Fayrite |
|------------------|---------------|-------------|--------------|------------------|---------------|----------------|
| Daily claim      | 25            | 0           | 0            | 750              | 0             | 0              |
| Daily explore*   | ? (not set)   | 1           | 0            | ?                | 30            | 0              |
| Dissolve (Epics) | ~             | ~           | ~            | ~                | ~             | ~              |

_Note: Daily explore rewards not fully listed; adjust per activity reward config._

---

## 10. Power Min/Max

- **Minimum possible unit power:**  
  - Common, Level 1, no breaks, base stats only, lowest possible rolls
- **Maximum possible unit power:**  
  - Deity, Level 200, 10 limit breaks, all stats perfect, maxed power formula

---

## 11. Admin Exploits / Abuse Scenarios

- Admins with currency grant can instantly max units, levels, and limit breaks
- Direct level manipulation can break XP progression (should always check cap enforcement)

---

## 12. Edge Case/Overflow Detection

- If player claims daily > once per cooldown, check for abuse
- Summon pity resets must always enforce after Supreme or Deity is pulled
- Level cap enforcement for both player and esprit must always check before allowing upgrades/limit breaks

---

## 13. Ultimate Min-Max Pathways

**To reach max collection and max unit:**
1. Claim all daily/weekly rewards
2. Run explore/other repeatable activities for extra currencies (if allowed)
3. Summon every day, dissolve low-rarity pulls, convert shards to fayrites
4. Funnel all resources into 1–2 core Esprits for maxing first
5. Run admin commands if eligible/tester

---

## 14. Pseudocode: Stat/Power Calculation (Universal)

```python
def calculate_esprit_stats(base_stats, level, breaks, rarity, config):
    level_mult = 1 + (level - 1) * config['level_multiplier_per_level']
    break_mult = float(config['limit_break_multiplier_base']) ** breaks
    rarity_mult = config['rarity_multipliers'][rarity]
    final_stats = {stat: base * level_mult * break_mult for stat, base in base_stats.items()}
    power = sum(final_stats[stat] * config['sigil_weights'][stat] for stat in final_stats) * rarity_mult
    return final_stats, power
```

---

## 15. “True” Payoff Timelines

- **F2P**: Expect to take years to reach full deck unless event rewards, powercreep, or admin boosts
- **P2W**: Unlimited pulls = instant max units, but still limited by in-game cap/upgrade/limit break materials

---

## 16. Full Config Dependency Map

- Change any of these: RE-CALCULATE ALL PATHS!
  - player_xp_curve
  - daily_rewards
  - activity_rewards
  - progression caps and thresholds
  - esprit_upgrade_system
  - limit_break_system
  - dissolve_rewards
  - summoning/pity
  - power/level/stat formulas
  - any new banner, new currency, new activity

