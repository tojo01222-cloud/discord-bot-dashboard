"""
Anti-Spam-System.

Zählt Nachrichten pro User in einem kurzen Zeitfenster. Wird der Schwellenwert
überschritten, werden die letzten Spam-Nachrichten gelöscht und der User kurz
in Timeout gesetzt. Zähler liegen im Arbeitsspeicher (siehe anti_nuke.py für
die Begründung).
"""
from __future__ import annotations

import datetime as dt
import logging
from collections import defaultdict, deque

import discord
from discord.ext import commands

from bot.config import config
from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, base_embed
from bot.utils.i18n import t
from bot.utils.db_helpers import (
    get_guild_language,
    get_security_settings,
    set_anti_spam_enabled,
    is_trusted_user,
    log_punishment,
)

log = logging.getLogger("bot.anti_spam")

THRESHOLD_COUNT = 5
THRESHOLD_WINDOW_SECONDS = 6
TIMEOUT_SECONDS = 300  # 5 Minuten


class AntiSpam(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # guild_id -> user_id -> deque[(timestamp, message)]
        self._message_log: dict[int, dict[int, deque]] = defaultdict(lambda: defaultdict(deque))
        self._punishing: set[tuple[int, int]] = set()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if not isinstance(message.author, discord.Member):
            return

        _, spam_enabled = await get_security_settings(message.guild.id)
        if not spam_enabled:
            return
        if message.author.id == config.BOT_OWNER_ID or message.author.id == message.guild.owner_id:
            return
        if await is_trusted_user(message.guild.id, message.author.id):
            return
        if message.author.guild_permissions.administrator:
            return

        now = dt.datetime.now(dt.timezone.utc).timestamp()
        bucket = self._message_log[message.guild.id][message.author.id]
        bucket.append((now, message))
        while bucket and now - bucket[0][0] > THRESHOLD_WINDOW_SECONDS:
            bucket.popleft()

        if len(bucket) >= THRESHOLD_COUNT:
            messages_to_delete = [m for _, m in bucket]
            bucket.clear()
            await self._punish(message.guild, message.author, message.channel, messages_to_delete)

    async def _punish(self, guild: discord.Guild, member: discord.Member,
                       channel: discord.abc.Messageable, messages: list[discord.Message]) -> None:
        key = (guild.id, member.id)
        if key in self._punishing:
            return
        self._punishing.add(key)
        try:
            lang = await get_guild_language(guild.id)

            # Nachrichten löschen (bulk_delete nur für Textkanäle mit <14 Tage alten Nachrichten)
            if isinstance(channel, discord.TextChannel):
                try:
                    await channel.delete_messages(messages)
                except (discord.Forbidden, discord.HTTPException):
                    for m in messages:
                        try:
                            await m.delete()
                        except discord.HTTPException:
                            pass

            try:
                await member.timeout(dt.timedelta(seconds=TIMEOUT_SECONDS), reason="Anti-Spam: zu viele Nachrichten")
            except discord.Forbidden:
                log.warning("Konnte %s in Guild %s nicht timeouten (fehlende Berechtigung).", member.id, guild.id)

            await log_punishment(guild.id, member.id, self.bot.user.id, "anti_spam_timeout",
                                  "Automatisch: zu viele Nachrichten in kurzer Zeit")

            embed = base_embed(t("security.nuke_alert_title", lang))
            embed.title = "🚨 Anti-Spam ausgelöst" if lang == "de" else "🚨 Anti-spam triggered"
            embed.color = discord.Color.orange()
            embed.description = t("security.spam_alert_desc", lang, user=member.mention)

            from bot.database.db import get_session
            from bot.database.models import GuildSettings
            async with get_session() as session:
                settings = await session.get(GuildSettings, guild.id)
                log_channel_id = settings.mod_log_channel_id if settings else 0
            if log_channel_id:
                log_channel = guild.get_channel(log_channel_id)
                if log_channel:
                    await log_channel.send(embed=embed)
        finally:
            self._punishing.discard(key)

    # ---------- Commands ----------

    @commands.hybrid_group(name="antispam", description="Anti-Spam-System verwalten.")
    @commands.guild_only()
    async def antispam(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @antispam.command(name="on", description="Aktiviert das Anti-Spam-System.")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def antispam_on(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        await set_anti_spam_enabled(ctx.guild.id, True)
        await ctx.send(embed=success_embed(t("security.antispam_enabled", lang)))

    @antispam.command(name="off", description="Deaktiviert das Anti-Spam-System.")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def antispam_off(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        await set_anti_spam_enabled(ctx.guild.id, False)
        await ctx.send(embed=success_embed(t("security.antispam_disabled", lang)))


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiSpam(bot))
