"""
Anti-Hack-System.

- /antihack on|off              -- System ein-/ausschalten (SERVER_ADMIN)
- /antihack_add <user|rolle>    -- von der Erkennung ausnehmen (SERVER_ADMIN)
- /antihack_liste                -- zeigt die Ausnahmeliste

Erkennung: postet ein Account innerhalb kurzer Zeit etwas mit Anhang oder Link
(z.B. Bilder) in mehrere VERSCHIEDENE Kanäle, gilt das als typisches Verhalten
eines gekaperten/kompromittierten Accounts (Self-Bot-Spam) -- der Account wird
automatisch gekickt, informiert per DM (best effort) und im Strafregister
vermerkt. Ganz normales Chatten in mehreren Kanälen OHNE Anhang/Link löst
NICHTS aus, um Fehlalarme bei normalen Usern zu vermeiden.
"""
import datetime as dt
import logging
import re
from collections import defaultdict, deque

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, error_embed, base_embed
from bot.utils.i18n import t
from bot.utils.db_helpers import (
    get_guild_language,
    get_anti_hack_enabled,
    set_anti_hack_enabled,
    is_anti_exempt,
    add_anti_exemption,
    remove_anti_exemption,
    get_anti_exemptions,
    log_punishment,
)
from bot.database.db import get_session
from bot.database.models import GuildSettings

log = logging.getLogger("bot.anti_hack")

# Schwellenwerte: X VERSCHIEDENE Kanäle mit Anhang/Link innerhalb von Y Sekunden.
DISTINCT_CHANNEL_THRESHOLD = 3
WINDOW_SECONDS = 15

_LINK_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)


def _looks_shareable(message: discord.Message) -> bool:
    """True, wenn die Nachricht etwas 'Teilbares' enthält (Anhang oder Link) --
    reines Chatten ohne das löst die Erkennung nie aus."""
    return bool(message.attachments) or bool(_LINK_RE.search(message.content or ""))


class AntiHack(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # guild_id -> user_id -> deque[(timestamp, channel_id)]
        self._activity: dict[int, dict[int, deque]] = defaultdict(lambda: defaultdict(deque))
        self._punishing: set[tuple[int, int]] = set()

    async def _is_exempt(self, member: discord.Member) -> bool:
        if member.bot or member.id == member.guild.owner_id or member.guild_permissions.administrator:
            return True
        if await is_anti_exempt(member.guild.id, "antihack", "user", member.id):
            return True
        for role in member.roles:
            if await is_anti_exempt(member.guild.id, "antihack", "role", role.id):
                return True
        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or not isinstance(message.author, discord.Member):
            return
        if not await get_anti_hack_enabled(message.guild.id):
            return
        if not _looks_shareable(message):
            return
        if await self._is_exempt(message.author):
            return

        now = dt.datetime.now(dt.timezone.utc).timestamp()
        bucket = self._activity[message.guild.id][message.author.id]
        bucket.append((now, message.channel.id))
        while bucket and now - bucket[0][0] > WINDOW_SECONDS:
            bucket.popleft()

        distinct_channels = {ch for _, ch in bucket}
        if len(distinct_channels) >= DISTINCT_CHANNEL_THRESHOLD:
            bucket.clear()
            await self._punish(message.guild, message.author, len(distinct_channels))

    async def _punish(self, guild: discord.Guild, member: discord.Member, channel_count: int) -> None:
        key = (guild.id, member.id)
        if key in self._punishing:
            return
        self._punishing.add(key)
        try:
            lang = await get_guild_language(guild.id)

            try:
                await member.send(t("antihack.kicked_dm", lang, guild=guild.name))
            except discord.Forbidden:
                pass  # DMs geschlossen -- kein Blocker für den Kick

            try:
                await member.kick(reason="Anti-Hack: verdächtiges kanalübergreifendes Spam-Verhalten")
            except discord.Forbidden:
                log.warning("Konnte %s in Guild %s nicht kicken (fehlende Berechtigung).", member.id, guild.id)
                return

            await log_punishment(guild.id, member.id, self.bot.user.id, "anti_hack_kick",
                                  f"Automatisch: identisches/teilbares Verhalten in {channel_count} Kanälen")

            embed = base_embed("🚨 Anti-Hack" if lang == "de" else "🚨 Anti-hack")
            embed.color = discord.Color.red()
            embed.description = t("antihack.alert", lang, user=member.mention, count=channel_count)

            async with get_session() as session:
                settings = await session.get(GuildSettings, guild.id)
                log_channel_id = settings.mod_log_channel_id if settings else 0
            if log_channel_id:
                channel = guild.get_channel(log_channel_id)
                if channel:
                    await channel.send(embed=embed)
        finally:
            self._punishing.discard(key)

    # ---------- Commands ----------
    @commands.hybrid_group(name="antihack", description="Anti-Hack-System verwalten.")
    @commands.guild_only()
    async def antihack(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @antihack.command(name="on", description="Aktiviert das Anti-Hack-System.")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def antihack_on(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        await set_anti_hack_enabled(ctx.guild.id, True)
        await ctx.send(embed=success_embed(t("anti.enabled", lang, feature="Anti-Hack")))

    @antihack.command(name="off", description="Deaktiviert das Anti-Hack-System.")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def antihack_off(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        await set_anti_hack_enabled(ctx.guild.id, False)
        await ctx.send(embed=success_embed(t("anti.disabled", lang, feature="Anti-Hack")))

    @commands.hybrid_command(name="antihack_add", description="Nimmt einen User oder eine Rolle von der Anti-Hack-Erkennung aus.")
    @app_commands.describe(user="Optional: ein User", rolle="Optional: eine Rolle")
    @commands.guild_only()
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def antihack_add(self, ctx: commands.Context, user: discord.Member = None, rolle: discord.Role = None):
        await _add_exemption(ctx, "antihack", "Anti-Hack", user, rolle)

    @commands.hybrid_command(name="antihack_liste", description="Zeigt die Anti-Hack-Ausnahmeliste.")
    @commands.guild_only()
    async def antihack_liste(self, ctx: commands.Context):
        await _list_exemptions(ctx, "antihack", "Anti-Hack")


async def _add_exemption(ctx: commands.Context, feature: str, label: str,
                          user: discord.Member = None, rolle: discord.Role = None) -> None:
    lang = await get_guild_language(ctx.guild.id)
    if not user and not rolle:
        await ctx.send(embed=error_embed(
            "Gib entweder einen User oder eine Rolle an." if lang == "de"
            else "Provide either a user or a role."))
        return

    target = user or rolle
    target_type = "user" if user else "role"
    target_mention = target.mention

    added = await add_anti_exemption(ctx.guild.id, feature, target_type, target.id, ctx.author.id)
    if added:
        await ctx.send(embed=success_embed(t("anti.exempt_added", lang, target=target_mention, feature=label)))
    else:
        await ctx.send(embed=error_embed(t("anti.exempt_already", lang, target=target_mention, feature=label)))


async def _list_exemptions(ctx: commands.Context, feature: str, label: str) -> None:
    lang = await get_guild_language(ctx.guild.id)
    entries = await get_anti_exemptions(ctx.guild.id, feature)
    if not entries:
        await ctx.send(embed=error_embed(t("anti.exempt_list_empty", lang, feature=label)))
        return

    lines = []
    for e in entries:
        mention = f"<@{e.target_id}>" if e.target_type == "user" else f"<@&{e.target_id}>"
        lines.append(mention)

    embed = base_embed(t("anti.exempt_list_title", lang, feature=label))
    embed.description = "\n".join(lines[:50])
    await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiHack(bot))
