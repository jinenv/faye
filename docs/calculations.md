# Nyxa Bot Calculation System - Complete Current Implementation

## Core System Architecture

The calculations use a three-layer multiplicative scaling system where each layer compounds with the others to create exponential power growth at high levels. **Current implementation uses Moonglow for Esprit upgrades and player progression gates for limit breaks.**

## Stat Calculation Foundation

The base stat calculation uses this formula:
Final Stat = Base Stat × Level Multiplier × Limit Break Multiplier

The level multiplier grows linearly at 5% per level:
level_multiplier = 1 + (current_level - 1) * 0.05

This creates a steady arithmetic progression where:
- Level 50: 3.45x base stats
- Level 100: 5.95x base stats  
- Level 200: 10.95x base stats

The limit break multiplier uses exponential growth:
limit_break_multiplier = 1.1^limit_breaks_performed

This provides 10% multiplicative boost per limit break that compounds dramatically at higher counts.

## Level Cap Progression System

The level cap system follows player progression gates (CURRENT IMPLEMENTATION):
Current Level Cap = Next Player Progression Threshold

Player progression thresholds:
- Level 1-9: Esprit cap 20
- Level 10-14: Esprit cap 30  
- Level 15-29: Esprit cap 50
- Level 30-39: Esprit cap 75
- Level 40-49: Esprit cap 100
- Level 50-64: Esprit cap 135
- Level 65-69: Esprit cap 150
- Level 70-74: Esprit cap 175
- Level 75-80: Esprit cap 200

Rarity determines absolute maximum progression:
- Common: 75 max (3 limit breaks possible: 20→30→50→75)
- Uncommon: 100 max (4 limit breaks possible)
- Rare: 100 max (4 limit breaks possible)
- Epic: 100 max (4 limit breaks possible)
- Celestial: 150 max (6 limit breaks possible)
- Supreme: 175 max (7 limit breaks possible)
- Deity: 200 max (9 limit breaks possible - full progression)

## Power Calculation (Sigil System)

The Sigil power calculation uses a weighted sum approach:

Power = (HP/4) + (ATK×2.5) + (DEF×2.5) + (SPD×3.0) + (Magic Resist×2.0) + 
       (Crit Rate×500) + (Block Rate×500) + (Dodge×600) + (Mana×0.5) + (Mana Regen×100)

Speed receives the highest weight at 3.0x because turn economy dominates combat systems. HP is divided by 4 because health pools are numerically larger than other stats.

After weighted calculation, rarity multipliers are applied:
- Common: 1.0x (no bonus)
- Uncommon: 1.1x (+10% power)
- Rare: 1.25x (+25% power)
- Epic: 1.4x (+40% power)
- Celestial: 1.6x (+60% power)
- Supreme: 1.8x (+80% power)
- Deity: 2.0x (+100% power)

## Moonglow Upgrade Cost System (CURRENT)

**Esprit upgrade formula using Moonglow:**
moonglow_cost = 15 + (current_level × 8)

This creates linear scaling with reasonable progression costs:
- Level 1→2: 23 Moonglow
- Level 10→11: 95 Moonglow  
- Level 25→26: 215 Moonglow
- Level 50→51: 415 Moonglow
- Level 75→76: 615 Moonglow
- Level 99→100: 807 Moonglow

**Total progression costs:**
- Levels 1→50: ~10,500 total Moonglow
- Levels 1→75: ~22,000 total Moonglow  
- Levels 1→100: ~40,000 total Moonglow

**Economic balance with dissolve rewards:**
- Common dissolve (50 Moonglow): ~2 early upgrades
- Epic dissolve (750 Moonglow): ~3-8 mid-level upgrades
- Deity dissolve (12,500 Moonglow): ~15-30 upgrades
- Full Epic progression: ~53 Epic dissolves OR 3 Deity dissolves

## Limit Break Cost Scaling Mathematics

The cost calculation uses a four-factor multiplicative system:
Total Cost = Base Cost × Rarity Multiplier × Level Multiplier × Previous Breaks Multiplier

Base costs:
- Essence: 200
- Moonglow: 500

Rarity multipliers:
- Common: 1.0x
- Uncommon: 1.5x
- Rare: 2.0x
- Epic: 3.0x
- Celestial: 5.0x
- Supreme: 7.0x
- Deity: 10.0x

Level scaling formula:
level_multiplier = 1 + (current_level / 50)

Previous breaks multiplier (exponential scaling):
previous_breaks_multiplier = 1.5^limit_breaks_performed

**Cost examples:**
- Epic Level 50, 1st break: 200 essence + 3,000 moonglow
- Epic Level 75, 2nd break: 200 essence + 6,750 moonglow
- Deity Level 100, 3rd break: 200 essence + 33,750 moonglow

## Player XP Requirements (CURRENT)

Player level XP formula:
xp_required = 100 × (next_level^1.5)

Examples:
- Level 1→2: 283 XP
- Level 10→11: 3,648 XP
- Level 50→51: 36,401 XP
- Level 79→80: 71,554 XP

**Auto-leveling system:** Players automatically level up when XP threshold is reached, with level-up embed notifications.

## Dissolve Rewards (CURRENT)

Fixed rewards per Esprit dissolved:
- Common: 50 Moonglow + 5 Essence
- Uncommon: 125 Moonglow + 12 Essence
- Rare: 300 Moonglow + 30 Essence
- Epic: 750 Moonglow + 75 Essence
- Celestial: 2,000 Moonglow + 200 Essence
- Supreme: 5,000 Moonglow + 500 Essence
- Deity: 12,500 Moonglow + 1,250 Essence

## Resource Flow Design (CURRENT)

**Primary Currencies:**
- **Moonglow**: Esprit upgrades + Limit breaks (premium resource)
- **Essence**: Limit breaks only (secondary resource)  
- **Nyxies**: Daily activities, shop purchases (common currency)
- **XP**: Player leveling only (separate from Esprit progression)

**Daily Income Sources:**
- Daily rewards: 25 Moonglow, 250 Nyxies
- Dissolving unwanted Esprits: 50-12,500 Moonglow
- Admin commands: For testing and debugging

**Economic Philosophy:**
- Casual players: 1-2 upgrades per day from daily income
- Active players: Dissolve management funds significant progression
- Limit breaks: Major milestone achievements requiring planning
- Collection vs progression: Meaningful choice between keeping and dissolving

## Real Performance Examples

Level 75 Epic Esprit with 2 limit breaks and 100 base attack:
- Level multiplier: 1 + (75-1) × 0.05 = 4.7x
- Limit break multiplier: 1.1² = 1.21x  
- Final attack stat: 100 × 4.7 × 1.21 = 568

Same progression costs:
- Levels 1→75: ~22,000 Moonglow (29 Epic dissolves)
- 2 limit breaks: ~10,000 Moonglow total
- **Total investment:** ~32,000 Moonglow (43 Epic dissolves)

## System Design Philosophy

The mathematical relationships create several important gameplay dynamics:

1. **Player progression gates Esprit progression** - encourages balanced advancement
2. **Limit breaks unlock next progression tiers** - creates meaningful milestone goals
3. **Moonglow scarcity drives collection management** - dissolve vs keep decisions
4. **Exponential limit break costs** - prevents infinite scaling while rewarding dedication
5. **Linear upgrade costs** - keeps daily progression accessible and predictable

The system balances accessibility (daily upgrades) with long-term goals (limit breaks and max-level Esprits) while creating meaningful resource management decisions.

## Current Implementation Status

**✅ Fully Working:**
- All stat calculations and power formulas
- Player progression and auto-leveling
- Limit break system with player gate progression
- Dissolve reward system
- Level cap enforcement in admin commands
- Collection and team management

**🔧 Needs Update:**
- `/esprit upgrade` command: Change from XP to Moonglow cost system
- XP removal: Eliminate Esprit XP from normal gameplay (keep admin-only)

**📋 Next Priorities:**
- Combat system implementation
- Player profile enhancements  
- Advanced progression analytics