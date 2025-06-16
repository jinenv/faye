# src/cogs/esprit_cog.py
import asyncio
import traceback
from typing import List, Literal, Optional
from enum import Enum

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# Assumes you have created these files in the specified directories
from src.views.shared.confirmation_view import ConfirmationView
from src.views.esprit.collection_view import EnhancedCollectionView
from src.views.esprit.dissolve_view import BulkDissolveView
from src.views.esprit.select_view import EspritSelectView

from src.database.db import get_session
from src.database.models import User, UserEsprit, EspritData
from src.utils.logger import get_logger
from src.utils.rate_limiter import RateLimiter
from src.utils import transaction_logger

logger = get_logger(__name__)

class TeamSlot(str, Enum):
    LEADER = "active_esprit_id"
    SUPPORT1 = "support1_esprit_id"
    SUPPORT2 = "support2_esprit_id"
    def get_icon(self) -> str:
        return {"LEADER": "👑", "SUPPORT1": "⚔️", "SUPPORT2": "🛡️"}.get(self.name, "⚪")

# ─── Main Cog Class ───────────────────────────────────────────────────

class EspritCog(commands.Cog):
    """Handles all Esprit-related commands and interactions."""

    # --- Command Group Definitions ---
    # This is the correct pattern: define groups as class attributes inside the Cog.
    esprit = app_commands.Group(name="esprit", description="Manage, view, and upgrade your powerful Esprits.")
    team = app_commands.Group(name="team", description="Manage your active Esprit team.", parent=esprit)

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.rate_limiter = RateLimiter(calls=10, period=60)

    # --- Helper Methods ---
    async def _handle_error(self, inter: discord.Interaction, error: Exception):
        err_id = id(error)
        command_name = inter.command.qualified_name if inter.command else "esprit command"
        logger.error(f"[{err_id}] Error in '{command_name}': {error}", exc_info=True)
        content = f"❌ An unexpected error occurred (ID: `{err_id}`)."
        try:
            if inter.response.is_done(): await inter.followup.send(content, ephemeral=True)
            else: await inter.response.send_message(content, ephemeral=True)
        except discord.errors.InteractionResponded:
            await inter.edit_original_response(content=content, view=None, embed=None) # Fallback

    async def _check_rl(self, inter: discord.Interaction) -> bool:
        if not await self.rate_limiter.check(str(inter.user.id)):
            wait = await self.rate_limiter.get_cooldown(str(inter.user.id))
            await inter.followup.send(f"⏳ Slow down! Try again in {wait}s.", ephemeral=True)
            return False
        return True

    async def _get_user_esprits(self, session, user_id: str) -> List[UserEsprit]:
        res = await session.execute(
            select(UserEsprit)
            .where(UserEsprit.owner_id == user_id)
            .options(selectinload(UserEsprit.esprit_data), selectinload(UserEsprit.owner))
        )
        return res.scalars().all()

    # --- Top-Level Esprit Commands ---

    @esprit.command(name="collection", description="Browse your collected Esprits.")
    async def collection(self, inter: discord.Interaction):
        try:
            await inter.response.defer()
            if not await self._check_rl(inter): return
            async with get_session() as s:
                esprits = await self._get_user_esprits(s, str(inter.user.id))
            if not esprits:
                return await inter.followup.send(embed=discord.Embed(title="🌱 Your Collection is Empty", description="Use `/summon` to get started!", color=discord.Color.blue()))
            
            view = EnhancedCollectionView(self.bot, esprits, inter.user.id)
            await view.send(inter)
        except Exception as e: await self._handle_error(inter, e)

    @esprit.command(name="upgrade", description="Spend Virelite to level up an Esprit.")
    @app_commands.describe(esprit_id="ID of the Esprit", levels="How many levels (1-10) or 'max'.")
    async def upgrade(self, inter: discord.Interaction, esprit_id: str, levels: str):
        try:
            await inter.response.defer()
            if not await self._check_rl(inter): return
            prog_cfg = self.bot.config.get("progression_settings", {})
            combat_cfg = self.bot.config.get("combat_settings", {})
            async with get_session() as s:
                user = await s.get(User, str(inter.user.id), with_for_update=True)
                if not user: return await inter.followup.send("❌ You need to `/start` first.", ephemeral=True)
                
                ue = await s.get(UserEsprit, esprit_id, with_for_update=True, options=[selectinload(UserEsprit.esprit_data), selectinload(UserEsprit.owner)])
                if not ue or ue.owner_id != str(inter.user.id): return await inter.followup.send("❌ Esprit not found or not yours.", ephemeral=True)
                
                cap = ue.get_level_cap(prog_cfg.get("progression", {}))
                if ue.current_level >= cap: return await inter.followup.send(f"❌ **{ue.esprit_data.name}** is at level cap ({cap}).", ephemeral=True)
                
                if levels.lower() == "max": levels_to_add = cap - ue.current_level
                else:
                    try:
                        n = int(levels)
                        if not (1 <= n <= 10): return await inter.followup.send("❌ Amount must be 1-10 or 'max'.", ephemeral=True)
                        levels_to_add = min(n, cap - ue.current_level)
                    except ValueError: return await inter.followup.send("❌ Invalid amount.", ephemeral=True)
                
                if levels_to_add <= 0: return await inter.followup.send("❌ Already at level cap.", ephemeral=True)
                
                cost_cfg = combat_cfg.get("esprit_upgrade_system", {}).get("cost_formula", {"base": 15, "level_multiplier": 8})
                total_cost = sum(cost_cfg['base'] + (lvl * cost_cfg['level_multiplier']) for lvl in range(ue.current_level, ue.current_level + levels_to_add))
                
                if user.virelite < total_cost: return await inter.followup.send(f"❌ Need **{total_cost:,}** Virelite, you have {user.virelite:,}.", ephemeral=True)
                
                old_level, old_pow = ue.current_level, ue.calculate_power(combat_cfg.get("power_calculation", {}), combat_cfg.get("stat_calculation", {}))
                user.virelite -= total_cost
                ue.current_level += levels_to_add
                ue.current_hp = ue.calculate_stat("hp", combat_cfg.get("stat_calculation", {}))
                await s.commit()

            new_pow = ue.calculate_power(combat_cfg.get("power_calculation", {}), combat_cfg.get("stat_calculation", {}))
            embed = discord.Embed(title="⭐ Upgrade Complete!", description=f"**{ue.esprit_data.name}** has grown stronger!", color=discord.Color.gold())
            embed.add_field(name="Level", value=f"{old_level} → **{ue.current_level}**", inline=True).add_field(name="Sigil Power", value=f"{old_pow:,} → **{new_pow:,}**", inline=True)
            embed.add_field(name="Virelite Spent", value=f"{total_cost:,}", inline=False)
            await inter.followup.send(embed=embed)
            transaction_logger.log_esprit_upgrade(inter, ue, old_level, total_cost)
        except Exception as e: await self._handle_error(inter, e)

    @esprit.command(name="limitbreak", description="Break an Esprit’s level cap to unlock greater power.")
    @app_commands.describe(esprit_id="The ID of the Esprit to limit break.")
    async def limitbreak(self, inter: discord.Interaction, esprit_id: str):
        try:
            await inter.response.defer()
            if not await self._check_rl(inter): return
            prog_cfg, combat_cfg = self.bot.config.get("progression_settings", {}), self.bot.config.get("combat_settings", {})
            lb_cfg = combat_cfg.get("limit_break_system", {})
            async with get_session() as s:
                user = await s.get(User, str(inter.user.id), with_for_update=True)
                if not user: return await inter.followup.send("❌ You need to `/start` first.", ephemeral=True)
                ue = await s.get(UserEsprit, esprit_id, with_for_update=True, options=[selectinload(UserEsprit.esprit_data), selectinload(UserEsprit.owner)])
                if not ue or ue.owner_id != str(inter.user.id): return await inter.followup.send("❌ Esprit not found or not yours.", ephemeral=True)
                can_break_info = ue.can_limit_break(prog_cfg.get("progression", {}))
                if not can_break_info["can_break"]: return await inter.followup.send(f"❌ Cannot limit break: {can_break_info['reason']}.", ephemeral=True)
                cost = ue.get_limit_break_cost(lb_cfg)
                if user.remna < cost["remna"] or user.virelite < cost["virelite"]: return await inter.followup.send(f"❌ Need **{cost['remna']:,} Remna** & **{cost['virelite']:,} Virelite**.", ephemeral=True)
                old_power = ue.calculate_power(combat_cfg.get("power_calculation", {}), combat_cfg.get("stat_calculation", {}))
                user.remna -= cost["remna"]; user.virelite -= cost["virelite"]
                ue.limit_breaks_performed += 1
                ue.stat_boost_multiplier *= lb_cfg.get("compound_rate", 1.1)
                await s.commit()
            new_power = ue.calculate_power(combat_cfg.get("power_calculation", {}), combat_cfg.get("stat_calculation", {}))
            embed = discord.Embed(title="🔓 LIMIT BREAK!", description=f"**{ue.esprit_data.name}** shattered its limits!", color=discord.Color.purple())
            embed.add_field(name="New Limit Breaks", value=f"{ue.limit_breaks_performed}", inline=True).add_field(name="Sigil Power", value=f"{old_power:,} → **{new_power:,}**", inline=True)
            embed.add_field(name="Cost", value=f"{cost['remna']:,} Remna, {cost['virelite']:,} Virelite", inline=False)
            await inter.followup.send(embed=embed)
            transaction_logger.log_limit_break(inter, ue, cost)
        except Exception as e: await self._handle_error(inter, e)

    @esprit.command(name="dissolve", description="Recycle Esprits for resources.")
    @app_commands.describe(esprit_id="ID of a single Esprit (omit for bulk).", multi="Dissolve multiple Esprits.", rarity_filter="[Bulk] Filter by rarity.")
    async def dissolve(self, inter: discord.Interaction, esprit_id: Optional[str] = None, multi: bool = False, rarity_filter: Optional[Literal["Common", "Uncommon", "Rare"]] = None):
        try:
            await inter.response.defer(ephemeral=True)
            if not await self._check_rl(inter): return
            if multi: await self._bulk_dissolve_handler(inter, rarity_filter)
            elif esprit_id: await self._single_dissolve_handler(inter, esprit_id)
            else: await inter.followup.send("❌ Provide an `esprit_id` or set `multi=True`.", ephemeral=True)
        except Exception as e: await self._handle_error(inter, e)

    async def _single_dissolve_handler(self, inter: discord.Interaction, esprit_id: str):
        # Implementation for dissolving a single Esprit
        # This helper keeps the main command logic clean
        rewards_cfg = self.bot.config.get('economy_settings', {}).get("dissolve_rewards", {})
        async with get_session() as s:
            user = await s.get(User, str(inter.user.id), with_for_update=True)
            if not user: return await inter.followup.send("❌ You need to `/start` first.", ephemeral=True)

            ue = await s.get(UserEsprit, esprit_id, with_for_update=True, options=[selectinload(UserEsprit.esprit_data)])
            if not ue or ue.owner_id != str(inter.user.id): return await inter.followup.send("❌ Esprit not found or not yours.", ephemeral=True)
            if ue.id in {user.active_esprit_id, user.support1_esprit_id, user.support2_esprit_id} or ue.locked:
                return await inter.followup.send("❌ Cannot dissolve a locked or equipped Esprit.", ephemeral=True)

            confirm = ConfirmationView(inter.user.id)
            await inter.followup.send(embed=discord.Embed(title="⚠️ Confirm Dissolve", description=f"Dissolve **{ue.esprit_data.name}**? This is final.", color=discord.Color.orange()), view=confirm, ephemeral=True)
            await confirm.wait()
            if not confirm.value: return

            reward = rewards_cfg.get(ue.esprit_data.rarity, {})
            v_gain, r_gain = reward.get("virelite", 0), reward.get("remna", 0)
            user.virelite += v_gain; user.remna += r_gain
            dissolved_copy = ue
            await s.delete(ue); await s.commit()

        embed = discord.Embed(title="♻️ Dissolve Complete", description=f"**{dissolved_copy.esprit_data.name}** dissolved.", color=discord.Color.green())
        embed.add_field(name="Resources Gained", value=f"🔷 **{v_gain:,}** Virelite\n🌀 **{r_gain:,}** Remna")
        await inter.edit_original_response(embed=embed, view=None)
        transaction_logger.log_esprit_dissolve(inter, [dissolved_copy], {"virelite": v_gain, "remna": r_gain})

    async def _bulk_dissolve_handler(self, inter: discord.Interaction, rarity_filter: Optional[str]):
        # Implementation for dissolving multiple Esprits
        rewards_cfg = self.bot.config.get('economy_settings', {}).get("dissolve_rewards", {})
        async with get_session() as s:
            user = await s.get(User, str(inter.user.id))
            if not user: return await inter.followup.send("❌ You need to `/start` first.", ephemeral=True)
            team_ids = {user.active_esprit_id, user.support1_esprit_id, user.support2_esprit_id}
            q = select(UserEsprit).where(UserEsprit.owner_id == str(inter.user.id), UserEsprit.locked == False, ~UserEsprit.id.in_(team_ids)).options(selectinload(UserEsprit.esprit_data))
            if rarity_filter: q = q.join(EspritData).where(EspritData.rarity == rarity_filter)
            esprits = (await s.execute(q.order_by(UserEsprit.current_level))).scalars().all()
        
        if not esprits: return await inter.followup.send("❌ No dissolvable Esprits found.", ephemeral=True)
        
        view = BulkDissolveView(esprits, inter.user.id)
        await inter.followup.send(embed=discord.Embed(title="♻️ Bulk Dissolve", description="Select Esprits to dissolve.", color=discord.Color.orange()), view=view, ephemeral=True)
        await view.wait()
        if not view.value or not view.selected_ids: return await inter.edit_original_response(content="Bulk dissolve cancelled.", embed=None, view=None)
        
        total_rewards, dissolved_for_log = {"virelite": 0, "remna": 0}, []
        async with get_session() as s:
            user = await s.get(User, str(inter.user.id), with_for_update=True)
            to_delete = (await s.execute(select(UserEsprit).where(UserEsprit.id.in_(view.selected_ids)).options(selectinload(UserEsprit.esprit_data)))).scalars().all()
            for e in to_delete:
                reward = rewards_cfg.get(e.esprit_data.rarity, {}); total_rewards["virelite"] += reward.get("virelite", 0); total_rewards["remna"] += reward.get("remna", 0)
                dissolved_for_log.append(e); await s.delete(e)
            user.virelite += total_rewards["virelite"]; user.remna += total_rewards["remna"]
            await s.commit()

        embed = discord.Embed(title="♻️ Bulk Dissolve Complete", description=f"Dissolved **{len(dissolved_for_log)}** Esprits.", color=discord.Color.green())
        embed.add_field(name="Resources Gained", value=f"🔷 **{total_rewards['virelite']:,}** Virelite\n🌀 **{total_rewards['remna']:,}** Remna")
        await inter.edit_original_response(embed=embed, view=None)
        transaction_logger.log_esprit_dissolve(inter, dissolved_for_log, total_rewards)

    # --- Team Sub-Commands ---
    @team.command(name="view", description="View your currently equipped team.")
    async def team_view(self, inter: discord.Interaction):
        try:
            await inter.response.defer(ephemeral=True)
            if not await self._check_rl(inter): return
            async with get_session() as s:
                user = await s.get(User, str(inter.user.id))
                if not user: return await inter.followup.send("❌ You need to `/start` first.", ephemeral=True)
                team_ids = {slot.value: getattr(user, slot.value) for slot in TeamSlot}
                esprit_map = {}
                if valid_ids := [eid for eid in team_ids.values() if eid]:
                    res = await s.execute(select(UserEsprit).where(UserEsprit.id.in_(valid_ids)).options(selectinload(UserEsprit.esprit_data)))
                    esprit_map = {e.id: e for e in res.scalars()}
            embed = discord.Embed(title=f"⚔️ {inter.user.display_name}'s Team", color=discord.Color.blue())
            total_power, power_cfg, stat_cfg = 0, self.bot.config.get("combat_settings", {}).get("power_calculation", {}), self.bot.config.get("combat_settings", {}).get("stat_calculation", {})
            for slot in TeamSlot:
                esprit = esprit_map.get(team_ids[slot.value])
                name, value = f"{slot.get_icon()} {slot.name.title()}", "_Empty_"
                if esprit:
                    power = esprit.calculate_power(power_cfg, stat_cfg); total_power += power
                    value = f"**{esprit.esprit_data.name}**\nLvl {esprit.current_level} | Sigil {power:,}"
                embed.add_field(name=name, value=value, inline=False)
            embed.set_footer(text=f"Total Team Power: {total_power:,}")
            await inter.followup.send(embed=embed)
        except Exception as e: await self._handle_error(inter, e)
    
    @team.command(name="set", description="Set an Esprit to an active team slot.")
    @app_commands.describe(slot="The team slot to fill.", esprit_id="ID of the Esprit to set (or 'clear').")
    async def team_set(self, inter: discord.Interaction, slot: TeamSlot, esprit_id: Optional[str] = None):
        try:
            await inter.response.defer(ephemeral=True)
            if not await self._check_rl(inter): return
            async with get_session() as s:
                user = await s.get(User, str(inter.user.id), with_for_update=True)
                if not user: return await inter.followup.send("❌ You need to `/start` first.", ephemeral=True)
                if not esprit_id:
                    esprits = await self._get_user_esprits(s, str(inter.user.id))
                    if not esprits: return await inter.followup.send("You have no Esprits to choose from.", ephemeral=True)
                    view = EspritSelectView(esprits, inter.user.id)
                    await inter.followup.send("Choose an Esprit for the slot:", view=view, ephemeral=True)
                    await view.wait()
                    if not view.chosen_esprit_id: return await inter.edit_original_response(content="Selection timed out.", view=None)
                    esprit_id = view.chosen_esprit_id
                
                if esprit_id.lower() in ['none', 'empty', 'clear']:
                    setattr(user, slot.value, None)
                    await s.commit()
                    return await inter.edit_original_response(content=f"✅ Slot **{slot.name.title()}** cleared.", view=None)
                
                ue = await s.get(UserEsprit, esprit_id, options=[selectinload(UserEsprit.esprit_data)])
                if not ue or ue.owner_id != str(inter.user.id): return await inter.edit_original_response(content="❌ Esprit not found or not yours.", view=None)
                
                team_ids = {s.value: getattr(user, s.value) for s in TeamSlot}
                if esprit_id in team_ids.values() and team_ids.get(slot.value) != esprit_id:
                    return await inter.edit_original_response(content="❌ Esprit is already in another slot.", view=None)
                setattr(user, slot.value, esprit_id)
                await s.commit()
                await inter.edit_original_response(content=f"✅ **{ue.esprit_data.name}** set as your **{slot.name.title()}**.", view=None)
        except Exception as e: await self._handle_error(inter, e)
        
    @team.command(name="optimize", description="Automatically equip your three strongest Esprits.")
    async def team_optimize(self, inter: discord.Interaction):
        try:
            await inter.response.defer()
            if not await self._check_rl(inter): return
            async with get_session() as s:
                user = await s.get(User, str(inter.user.id), with_for_update=True)
                if not user: return await inter.followup.send("❌ You need to `/start` first.", ephemeral=True)
                esprits = await self._get_user_esprits(s, str(inter.user.id))
                if not esprits: return await inter.followup.send("❌ You have no Esprits to form a team.", ephemeral=True)
                power_cfg, stat_cfg = self.bot.config.get("combat_settings", {}).get("power_calculation", {}), self.bot.config.get("combat_settings", {}).get("stat_calculation", {})
                esprits.sort(key=lambda e: e.calculate_power(power_cfg, stat_cfg), reverse=True)
                
                user.active_esprit_id = esprits[0].id if len(esprits) > 0 else None
                user.support1_esprit_id = esprits[1].id if len(esprits) > 1 else None
                user.support2_esprit_id = esprits[2].id if len(esprits) > 2 else None
                await s.commit()

                lines, total_power = [], 0
                for i, ue in enumerate(esprits[:3]):
                    slot = [TeamSlot.LEADER, TeamSlot.SUPPORT1, TeamSlot.SUPPORT2][i]
                    power = ue.calculate_power(power_cfg, stat_cfg); total_power += power
                    lines.append(f"**{slot.get_icon()} {slot.name.title()}:** {ue.esprit_data.name} (Sigil: {power:,})")
                
                embed = discord.Embed(title="✅ Team Optimized!", description="Your strongest Esprits are now equipped.", color=discord.Color.green())
                embed.add_field(name="New Team", value="\n".join(lines), inline=False).set_footer(text=f"Total Team Power: {total_power:,}")
                await inter.followup.send(embed=embed)
        except Exception as e: await self._handle_error(inter, e)

# ─── Cog Loader Boilerplate ────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(EspritCog(bot))
    logger.info("✅ EspritCog loaded")