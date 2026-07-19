"""
Info- und Hilfe-Befehle. Dient als REFERENZ-Cog für alle weiteren Module:
Jeder Command wird als `hybrid_command` gebaut -> funktioniert automatisch
sowohl als /befehl (Slash) als auch als !befehl (Prefix), ohne doppelten Code.
"""
import discord
from discord.ext import commands

from bot.database.db import get_session
from bot.database.models import GuildSettings
from bot.utils.embeds import base_embed
from bot.utils.i18n import t
from sqlalchemy import select


async def get_guild_language(guild_id: int) -> str:
    async with get_session() as session:
        settings = await session.get(GuildSettings, guild_id)
        return settings.language if settings else "de"


class InfoHelp(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="help", description="Zeigt alle verfügbaren Befehle mit Beschreibung.")
    async def help_command(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id) if ctx.guild else "de"

        embed = base_embed(t("help.title", lang))
        # In den nächsten Phasen wird das automatisch aus allen geladenen Cogs
        # gruppiert nach Kategorie generiert (Moderation, Team, Musik, Fun, ...).
        # Für das Grundgerüst hier eine statische Vorschau:
        embed.add_field(
            name="🛡️ Moderation" if lang == "de" else "🛡️ Moderation",
            value="`/kick` `/ban` `/timeout` `/warn` ...",
            inline=False,
        )
        embed.add_field(
            name="👥 Team" if lang == "de" else "👥 Team",
            value="`/uprank` `/downrank` `/teamkick` `/teamliste` ...",
            inline=False,
        )
        embed.add_field(
            name="🎵 Musik" if lang == "de" else "🎵 Music",
            value="`/play` `/skip` `/queue` ...",
            inline=False,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="serverinfo", description="Zeigt Informationen über diesen Server.")
    @commands.guild_only()
    async def serverinfo(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        guild = ctx.guild

        embed = base_embed(t("serverinfo.title", lang))
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Name", value=guild.name, inline=True)
        embed.add_field(name="Owner", value=str(guild.owner), inline=True)
        embed.add_field(name="Mitglieder" if lang == "de" else "Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Erstellt am" if lang == "de" else "Created at",
                         value=discord.utils.format_dt(guild.created_at, style="D"), inline=True)
        embed.add_field(name="Rollen" if lang == "de" else "Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Kanäle" if lang == "de" else "Channels", value=str(len(guild.channels)), inline=True)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(InfoHelp(bot))
