"""
Geburtstags-System.

- /geburtstag kanal <kanal>              -- legt den Gratulations-Kanal fest (SERVER_ADMIN)
- /geburtstag setzen <tag> <monat>        -- hinterlegt deinen Geburtstag (nur Tag+Monat, kein Jahr)
- /geburtstag liste                        -- zeigt alle hinterlegten Geburtstage dieses Servers

Prüft stündlich (siehe _daily_check_loop), ob heute jemand Geburtstag hat,
und gratuliert automatisch im eingerichteten Kanal. Bewusst KEIN Geburtsjahr
gespeichert -- nur Tag und Monat, aus Datenschutzgründen.
"""
import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, error_embed, base_embed
from bot.utils.db_helpers import (
    get_guild_language,
    get_birthday_channel,
    set_birthday_channel,
    set_birthday,
    get_birthdays_for_guild,
    get_todays_birthdays,
    mark_birthday_announced,
)


class Birthdays(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self._daily_check_loop.start()

    def cog_unload(self) -> None:
        self._daily_check_loop.cancel()

    @tasks.loop(hours=1)
    async def _daily_check_loop(self) -> None:
        """Prüft stündlich (nicht nur einmal um Mitternacht -- falls der Bot
        genau dann offline ist, würde sonst ein ganzer Geburtstag verpasst).
        mark_birthday_announced verhindert doppelte Gratulationen am selben Tag."""
        now = dt.datetime.utcnow()
        todays = await get_todays_birthdays(now.day, now.month, now.year)
        for birthday in todays:
            guild = self.bot.get_guild(birthday.guild_id)
            if not guild:
                continue
            channel_id = await get_birthday_channel(birthday.guild_id)
            if not channel_id:
                continue
            channel = guild.get_channel(channel_id)
            if not channel:
                continue
            member = guild.get_member(birthday.user_id)
            name = member.mention if member else f"<@{birthday.user_id}>"
            lang = await get_guild_language(birthday.guild_id)
            try:
                await channel.send(
                    f"🎉 Alles Gute zum Geburtstag, {name}! 🎂" if lang == "de"
                    else f"🎉 Happy Birthday, {name}! 🎂"
                )
            except discord.Forbidden:
                pass
            await mark_birthday_announced(birthday.id, now.year)

    @_daily_check_loop.before_loop
    async def _before_daily_check(self) -> None:
        await self.bot.wait_until_ready()

    @commands.hybrid_group(name="geburtstag", description="Geburtstags-System verwalten.")
    @commands.guild_only()
    async def geburtstag(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @geburtstag.command(name="kanal", description="Legt den Kanal für Geburtstags-Gratulationen fest.")
    @app_commands.describe(kanal="Der Zielkanal")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def geburtstag_kanal(self, ctx: commands.Context, kanal: discord.TextChannel):
        lang = await get_guild_language(ctx.guild.id)
        await set_birthday_channel(ctx.guild.id, kanal.id)
        await ctx.send(embed=success_embed(
            f"Geburtstags-Kanal auf {kanal.mention} gesetzt." if lang == "de"
            else f"Birthday channel set to {kanal.mention}."))

    @geburtstag.command(name="setzen", description="Hinterlegt deinen Geburtstag (nur Tag und Monat).")
    @app_commands.describe(tag="Tag (1-31)", monat="Monat (1-12)")
    @commands.guild_only()
    async def geburtstag_setzen(self, ctx: commands.Context, tag: int, monat: int):
        lang = await get_guild_language(ctx.guild.id)
        if monat < 1 or monat > 12 or tag < 1 or tag > 31:
            await ctx.send(embed=error_embed(
                "Ungültiges Datum." if lang == "de" else "Invalid date."), ephemeral=True)
            return
        try:
            dt.date(2024, monat, tag)  # Schaltjahr als Referenz, damit auch 29. Februar gültig ist
        except ValueError:
            await ctx.send(embed=error_embed(
                "Dieses Datum gibt es nicht." if lang == "de" else "That date doesn't exist."), ephemeral=True)
            return

        await set_birthday(ctx.guild.id, ctx.author.id, tag, monat)
        await ctx.send(embed=success_embed(
            f"Geburtstag gespeichert: {tag}.{monat}." if lang == "de"
            else f"Birthday saved: {monat}/{tag}."), ephemeral=True)

    @geburtstag.command(name="liste", description="Zeigt alle hinterlegten Geburtstage dieses Servers.")
    async def geburtstag_liste(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        birthdays = await get_birthdays_for_guild(ctx.guild.id)
        if not birthdays:
            await ctx.send(embed=error_embed(
                "Noch keine Geburtstage hinterlegt." if lang == "de" else "No birthdays saved yet."))
            return

        sorted_birthdays = sorted(birthdays, key=lambda b: (b.month, b.day))
        embed = base_embed("🎂 Geburtstage" if lang == "de" else "🎂 Birthdays")
        embed.description = "\n".join(f"{b.day}.{b.month} — <@{b.user_id}>" for b in sorted_birthdays[:30])
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Birthdays(bot))
