"""
Anti-Nuke-System.

Erkennt destruktive Massenaktionen (viele Kanal-Löschungen, Rollen-Löschungen
oder Bans in kurzer Zeit) über die Audit-Log-Einträge und schränkt den
Verursacher automatisch ein (alle Rollen entfernt), statt dem Server beim
Zusehen zuzusehen, wie er "genuked" wird.

Wichtig zur Funktionsweise:
- Discord liefert bei on_guild_channel_delete/on_guild_role_delete KEINEN
  Verursacher direkt mit, daher wird kurz danach der Audit-Log abgefragt.
- Server-Owner, der eingetragene BOT_OWNER und Einträge in der
  TrustedUser-Whitelist lösen die Erkennung nie aus.
- Die Zähler liegen bewusst im Arbeitsspeicher (nicht in der DB), da es sich
  um kurzlebige Zeitfenster (Sekunden) handelt — bei Bot-Neustart ist das
  unkritisch, da ein Angriff dann ohnehin neu beginnen müsste.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
from collections import defaultdict, deque

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import config
from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, error_embed, base_embed
from bot.utils.i18n import t
from bot.utils.db_helpers import (
    get_guild_language,
    get_security_settings,
    set_anti_nuke_enabled,
    is_trusted_user,
    add_trusted_user,
    remove_trusted_user,
    get_trusted_users,
    log_punishment,
)

log = logging.getLogger("bot.anti_nuke")

# Schwellenwerte: X Aktionen innerhalb von Y Sekunden lösen den Schutz aus.
THRESHOLD_COUNT = 3
THRESHOLD_WINDOW_SECONDS = 10


class AntiNuke(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # guild_id -> user_id -> Zeitstempel der letzten Aktionen
        self._action_log: dict[int, dict[int, deque]] = defaultdict(lambda: defaultdict(deque))
        # Verhindert doppelte Bestrafung, während bereits eine Reaktion läuft
        self._punishing: set[tuple[int, int]] = set()

    async def _is_exempt(self, guild: discord.Guild, user_id: int) -> bool:
        if user_id == guild.owner_id or user_id == config.BOT_OWNER_ID or user_id == self.bot.user.id:
            return True
        return await is_trusted_user(guild.id, user_id)

    async def _get_audit_actor(self, guild: discord.Guild, action: discord.AuditLogAction) -> discord.Member | None:
        try:
            async for entry in guild.audit_logs(limit=1, action=action):
                # Nur akzeptieren, wenn der Eintrag frisch ist (letzte 5 Sekunden)
                if (dt.datetime.now(dt.timezone.utc) - entry.created_at).total_seconds() < 5:
                    return entry.user if isinstance(entry.user, discord.Member) else guild.get_member(entry.user.id)
        except discord.Forbidden:
            log.warning("Fehlende Berechtigung 'View Audit Log' in Guild %s", guild.id)
        return None

    async def _register_action(self, guild: discord.Guild, actor: discord.Member, action_name: str) -> None:
        enabled, _ = await get_security_settings(guild.id)
        if not enabled:
            return
        if await self._is_exempt(guild, actor.id):
            return

        now = dt.datetime.now(dt.timezone.utc).timestamp()
        bucket = self._action_log[guild.id][actor.id]
        bucket.append(now)
        while bucket and now - bucket[0] > THRESHOLD_WINDOW_SECONDS:
            bucket.popleft()

        if len(bucket) >= THRESHOLD_COUNT:
            bucket.clear()
            await self._punish(guild, actor, action_name)

    async def _punish(self, guild: discord.Guild, actor: discord.Member, action_name: str) -> None:
        key = (guild.id, actor.id)
        if key in self._punishing:
            return
        self._punishing.add(key)
        try:
            lang = await get_guild_language(guild.id)
            removable_roles = [r for r in actor.roles if r != guild.default_role and r < guild.me.top_role]
            if removable_roles:
                try:
                    await actor.remove_roles(*removable_roles, reason="Anti-Nuke: verdächtige Massenaktionen")
                except discord.Forbidden:
                    log.warning("Konnte Rollen von %s in Guild %s nicht entfernen (fehlende Berechtigung).",
                                actor.id, guild.id)

            await log_punishment(guild.id, actor.id, self.bot.user.id, "anti_nuke_action",
                                  f"Automatisch ausgelöst durch: {action_name}")

            embed = base_embed(t("security.nuke_alert_title", lang))
            embed.color = discord.Color.red()
            embed.description = t("security.nuke_alert_desc", lang, user=actor.mention, action=action_name)

            from bot.database.db import get_session
            from bot.database.models import GuildSettings
            async with get_session() as session:
                settings = await session.get(GuildSettings, guild.id)
                log_channel_id = settings.mod_log_channel_id if settings else 0

            if log_channel_id:
                channel = guild.get_channel(log_channel_id)
                if channel:
                    await channel.send(embed=embed)
        finally:
            self._punishing.discard(key)

    # ---------- Event-Listener ----------

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        actor = await self._get_audit_actor(channel.guild, discord.AuditLogAction.channel_delete)
        if actor:
            await self._register_action(channel.guild, actor, "Kanal-Löschungen")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        actor = await self._get_audit_actor(role.guild, discord.AuditLogAction.role_delete)
        if actor:
            await self._register_action(role.guild, actor, "Rollen-Löschungen")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        actor = await self._get_audit_actor(guild, discord.AuditLogAction.ban)
        if actor:
            await self._register_action(guild, actor, "Massen-Bans")

    # ---------- Commands ----------

    @commands.hybrid_group(name="antinuke", description="Anti-Nuke-System verwalten.")
    @commands.guild_only()
    async def antinuke(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @antinuke.command(name="on", description="Aktiviert das Anti-Nuke-System.")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def antinuke_on(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        await set_anti_nuke_enabled(ctx.guild.id, True)
        await ctx.send(embed=success_embed(t("security.antinuke_enabled", lang)))

    @antinuke.command(name="off", description="Deaktiviert das Anti-Nuke-System.")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def antinuke_off(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        await set_anti_nuke_enabled(ctx.guild.id, False)
        await ctx.send(embed=success_embed(t("security.antinuke_disabled", lang)))

    @antinuke.command(name="trust", description="Fügt einen User zur Anti-Nuke-Whitelist hinzu.")
    @app_commands.describe(member="Der zu vertrauende User")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def antinuke_trust(self, ctx: commands.Context, member: discord.Member):
        lang = await get_guild_language(ctx.guild.id)
        added = await add_trusted_user(ctx.guild.id, member.id, ctx.author.id)
        if added:
            await ctx.send(embed=success_embed(t("security.trusted_added", lang, user=member.mention)))
        else:
            await ctx.send(embed=error_embed(t("security.trusted_already", lang, user=member.mention)))

    @antinuke.command(name="untrust", description="Entfernt einen User von der Anti-Nuke-Whitelist.")
    @app_commands.describe(member="Der User")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def antinuke_untrust(self, ctx: commands.Context, member: discord.Member):
        lang = await get_guild_language(ctx.guild.id)
        removed = await remove_trusted_user(ctx.guild.id, member.id)
        if removed:
            await ctx.send(embed=success_embed(t("security.trusted_removed", lang, user=member.mention)))
        else:
            await ctx.send(embed=error_embed(t("security.trusted_not_found", lang, user=member.mention)))

    @antinuke.command(name="trustlist", description="Zeigt die Anti-Nuke-Whitelist.")
    async def antinuke_trustlist(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        entries = await get_trusted_users(ctx.guild.id)
        if not entries:
            await ctx.send(embed=error_embed(t("security.trusted_list_empty", lang)))
            return
        embed = base_embed(t("security.trusted_list_title", lang))
        embed.description = "\n".join(f"<@{e.user_id}>" for e in entries[:50])
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiNuke(bot))
