"""
Warteraum-System.

- /warteraum set <voice-kanal> <text-kanal>   -- legt Warteraum + Melde-Kanal fest (SERVER_ADMIN)
- /warteraum clear                             -- hebt die Einrichtung auf (SERVER_ADMIN)

Sobald jemand dem konfigurierten Sprachkanal (Warteraum) beitritt, sendet der
Bot automatisch eine Nachricht in den festgelegten Textkanal, dass diese
Person Hilfe braucht -- wie ursprünglich gewünscht.
"""
import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, base_embed
from bot.utils.i18n import t
from bot.utils.db_helpers import get_guild_language, get_or_create_guild_settings, get_guild_settings_snapshot
from bot.database.db import get_session


class Warteraum(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_group(name="warteraum", description="Warteraum-System verwalten.")
    @commands.guild_only()
    async def warteraum(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @warteraum.command(name="set", description="Legt den Warteraum-Sprachkanal und den Melde-Textkanal fest.")
    @app_commands.describe(voice="Der Sprachkanal, der als Warteraum dient",
                            text="Der Textkanal, in dem Meldungen erscheinen")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def warteraum_set(self, ctx: commands.Context, voice: discord.VoiceChannel, text: discord.TextChannel):
        lang = await get_guild_language(ctx.guild.id)
        async with get_session() as session:
            settings = await get_or_create_guild_settings(session, ctx.guild.id)
            settings.waiting_room_voice_channel_id = voice.id
            settings.waiting_room_notify_channel_id = text.id
            await session.commit()

        await ctx.send(embed=success_embed(t("warteraum.set", lang, voice=voice.mention, text=text.mention)))

    @warteraum.command(name="clear", description="Hebt die Warteraum-Einrichtung auf.")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def warteraum_clear(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        async with get_session() as session:
            settings = await get_or_create_guild_settings(session, ctx.guild.id)
            settings.waiting_room_voice_channel_id = 0
            settings.waiting_room_notify_channel_id = 0
            await session.commit()

        await ctx.send(embed=success_embed(t("warteraum.cleared", lang)))

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                     after: discord.VoiceState):
        if member.bot:
            return
        # Nur reagieren, wenn der Kanal NEU betreten wurde (nicht bei Stumm/Deaf-Änderungen
        # im selben Kanal, und nicht wenn jemand den Kanal nur verlässt).
        if after.channel is None or before.channel == after.channel:
            return

        guild = after.channel.guild
        snapshot = await get_guild_settings_snapshot(guild.id)
        waiting_room_id = snapshot["waiting_room_voice_channel_id"]
        notify_channel_id = snapshot["waiting_room_notify_channel_id"]
        lang = snapshot["language"]

        if not waiting_room_id or after.channel.id != waiting_room_id:
            return
        if not notify_channel_id:
            return

        notify_channel = guild.get_channel(notify_channel_id)
        if not notify_channel:
            return

        embed = base_embed("🙋 Warteraum" if lang == "de" else "🙋 Waiting room")
        embed.description = t("warteraum.notify", lang, user=member.mention, channel=after.channel.mention)
        try:
            await notify_channel.send(embed=embed)
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Warteraum(bot))
