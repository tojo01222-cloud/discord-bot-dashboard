"""
Anti-Werbung-System.

- /antiwerbung on|off              -- System ein-/ausschalten (SERVER_ADMIN)
- /antiwerbung_add <user|rolle>    -- darf Links posten, von der Erkennung ausgenommen (SERVER_ADMIN)
- /antiwerbung_liste                -- zeigt die Ausnahmeliste

Postet ein nicht ausgenommener User einen Link (egal welchen), wird die
Nachricht sofort gelöscht und eskalierend bestraft, pro User hochgezählt und
dauerhaft gespeichert (siehe AntiWerbungStrike):
  1. Verstoß -> 1 Stunde Timeout
  2. Verstoß -> 1 Tag Timeout
  3. Verstoß -> 7 Tage Timeout
  4. Verstoß (und jeder weitere) -> Kick

Server-Administratoren, der Server-Owner und explizit über /antiwerbung_add
ausgenommene User/Rollen sind von der Erkennung ausgenommen (dürfen frei
Links posten).
"""
import datetime as dt
import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed
from bot.utils.i18n import t
from bot.utils.db_helpers import (
    get_guild_language,
    get_anti_werbung_enabled,
    set_anti_werbung_enabled,
    is_anti_exempt,
    bump_anti_werbung_strike,
    log_punishment,
)
from bot.database.db import get_session
from bot.database.models import GuildSettings
from bot.cogs.anti_hack import _add_exemption, _list_exemptions

log = logging.getLogger("bot.anti_werbung")

_LINK_RE = re.compile(r"https?://\S+|www\.\S+|discord\.gg/\S+", re.IGNORECASE)

# Eskalationsstufen: Verstoß-Nummer -> Timeout-Dauer. Alles ab der letzten
# definierten Stufe + 1 (hier also ab dem 4. Verstoß) führt zum Kick.
ESCALATION = {
    1: dt.timedelta(hours=1),
    2: dt.timedelta(days=1),
    3: dt.timedelta(days=7),
}


class AntiWerbung(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _is_exempt(self, member: discord.Member) -> bool:
        if member.bot or member.id == member.guild.owner_id or member.guild_permissions.administrator:
            return True
        if await is_anti_exempt(member.guild.id, "antiwerbung", "user", member.id):
            return True
        for role in member.roles:
            if await is_anti_exempt(member.guild.id, "antiwerbung", "role", role.id):
                return True
        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or not isinstance(message.author, discord.Member):
            return
        if not await get_anti_werbung_enabled(message.guild.id):
            return
        if not _LINK_RE.search(message.content or ""):
            return
        if await self._is_exempt(message.author):
            return

        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        await self._punish(message.guild, message.author, message.channel)

    async def _punish(self, guild: discord.Guild, member: discord.Member,
                       channel: discord.abc.Messageable) -> None:
        lang = await get_guild_language(guild.id)
        count = await bump_anti_werbung_strike(guild.id, member.id)

        duration = ESCALATION.get(count)
        if duration is not None:
            consequence_key = f"antiwerbung.consequence_{count}"
            action = "timeout"
            try:
                await member.timeout(duration, reason=f"Anti-Werbung: unautorisierter Link (Verstoß Nr. {count})")
            except discord.Forbidden:
                log.warning("Konnte %s in Guild %s nicht timeouten (fehlende Berechtigung).", member.id, guild.id)
        else:
            consequence_key = "antiwerbung.consequence_4"
            action = "kick"
            try:
                await member.kick(reason=f"Anti-Werbung: unautorisierter Link (Verstoß Nr. {count})")
            except discord.Forbidden:
                log.warning("Konnte %s in Guild %s nicht kicken (fehlende Berechtigung).", member.id, guild.id)

        consequence_text = t(consequence_key, lang)

        try:
            await member.send(t("antiwerbung.deleted_dm", lang, guild=guild.name, count=count,
                                 consequence=consequence_text))
        except discord.Forbidden:
            pass

        await log_punishment(
            guild.id, member.id, self.bot.user.id, f"anti_werbung_{action}",
            f"Automatisch: unautorisierter Link (Verstoß Nr. {count})",
        )

        try:
            await channel.send(t("antiwerbung.alert", lang, user=member.mention, count=count,
                                  consequence=consequence_text))
        except discord.Forbidden:
            pass

        async with get_session() as session:
            settings = await session.get(GuildSettings, guild.id)
            log_channel_id = settings.mod_log_channel_id if settings else 0
        if log_channel_id:
            log_channel = guild.get_channel(log_channel_id)
            if log_channel and log_channel.id != getattr(channel, "id", None):
                try:
                    await log_channel.send(t("antiwerbung.alert", lang, user=member.mention, count=count,
                                              consequence=consequence_text))
                except discord.Forbidden:
                    pass

    # ---------- Commands ----------
    @commands.hybrid_group(name="antiwerbung", description="Anti-Werbung-System verwalten.")
    @commands.guild_only()
    async def antiwerbung(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @antiwerbung.command(name="on", description="Aktiviert das Anti-Werbung-System.")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def antiwerbung_on(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        await set_anti_werbung_enabled(ctx.guild.id, True)
        await ctx.send(embed=success_embed(t("anti.enabled", lang, feature="Anti-Werbung")))

    @antiwerbung.command(name="off", description="Deaktiviert das Anti-Werbung-System.")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def antiwerbung_off(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        await set_anti_werbung_enabled(ctx.guild.id, False)
        await ctx.send(embed=success_embed(t("anti.disabled", lang, feature="Anti-Werbung")))

    @commands.hybrid_command(name="antiwerbung_add", description="Erlaubt einem User oder einer Rolle, Links zu posten.")
    @app_commands.describe(user="Optional: ein User", rolle="Optional: eine Rolle")
    @commands.guild_only()
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def antiwerbung_add(self, ctx: commands.Context, user: discord.Member = None, rolle: discord.Role = None):
        await _add_exemption(ctx, "antiwerbung", "Anti-Werbung", user, rolle)

    @commands.hybrid_command(name="antiwerbung_liste", description="Zeigt die Anti-Werbung-Ausnahmeliste.")
    @commands.guild_only()
    async def antiwerbung_liste(self, ctx: commands.Context):
        await _list_exemptions(ctx, "antiwerbung", "Anti-Werbung")


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiWerbung(bot))
