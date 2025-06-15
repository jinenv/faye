# Faye: Revised Combat & Progression Directive

This document outlines the design for Faye's core gameplay loops, progression systems, and economy. It has been updated to reflect the current, verified currency and crafting systems.

## Team Structure
- **3-Esprit Parties:** 1 Main Fighter + 2 Support.
- **Main Esprit:** The active combatant, visible in the UI, and the primary recipient of commands.
- **Support Esprits:** Provide passive bonuses and secondary skills to the main fighter.
- **Class System:** Guardian, Destroyer, Mystic, Support.
- **Class Synergies:** Future implementation of team bonuses for specific class combinations.

## Skill System
- **Esprit Abilities:** Each Esprit will have 2 active abilities (Main + Secondary).
- **Main Skill:** A high-impact, signature ability with a significant MP cost and long cooldown.
- **Secondary Skill:** A lower-cost, shorter-cooldown ability focused on utility.
- **Combat Options:** The main fighter will have access to its own two skills, plus the secondary skills of its two supports, for a total of 4 available abilities per combat encounter.

## Combat Flow
- **Turn-Based:** The initial implementation will be Player vs. Environment (PvE), focused on 1v1 encounters.
- **Interface:** A `discord.ui.View` with buttons or a dropdown will be used to select from available skills.
- **Pacing:** Battles are designed to be fast-paced, resolving in 2-4 turns.
- **Feedback:** The UI will provide clear visual feedback for damage numbers, status effects, and other combat events.

## Core Progression Commands

### /explore
- A repeatable, low-intensity command with a short cooldown.
- **Function:** Serves as the primary method for players to engage with the world and earn resources.
- **Rewards:** Guaranteed to reward `Fayrite Shards` and `Faylen`. Has a chance to reward `Remna` and other materials.

### /tower
- A future, structured PvE challenge with progressively difficult floors.
- **Function:** Acts as a primary progression path and a goal for players to build their teams towards.
- **Rewards:** Grants major `Fayrite` and `Virelite` bonuses at milestone floors.

### /trial
- A PVE challenge that directly tests a player's strength and bravery.
- **Function** Acts as the player "limit break" system.
- **Unlocks** a player level much the same way that esprits are locked by level.

## Economy & Progression: Verified System

This section details the confirmed, implemented multi-currency economy.

### Confirmed Currency Roles
- **Faylen:** The universal "soft currency." Used for general purposes, potentially in a future shop or for player-to-player trading.
- **Virelite:** The dedicated "enhancement currency." Its sole purpose is to upgrade Esprits.
- **Fayrite Shards:** The raw "summoning material." This is the primary reward from activities like `/explore`. It is not used directly for summoning.
- **Fayrites:** The regular "summoning currency." It cannot be earned directly and must be crafted.
- **Ethryl:** The premium "summon currency." It is earned through `/daily` and dedicated `combat commands`.
- **Remna:** A tiered set of crafting materials for limit breaking an esprit.

### The Crafting & Summoning Loop
The core economic loop for acquiring new Esprits is now implemented and verified:
1.  Players run the `/explore` command to earn **Fayrite Shards**.
2.  Players use the `/craft fayrite` command to convert their shards into whole **Fayrites**.
3.  Players use their crafted **Fayrites** in the `/summon` command to acquire new Esprits.
4.  This creates a clear, engaging progression: **Play -> Gather -> Craft -> Summon**.

### Milestone & Long-Term Goals
- **Sigil Power:** A future metric representing a player's total account power across all owned Esprits. This will be used for milestone rewards and leaderboards.
- **Leaderboards:** A global ranking system based on Sigil Power or Tower Floor progression to drive social competition.