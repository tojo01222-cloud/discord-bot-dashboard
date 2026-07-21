"""
Event-Ankündigungen, Countdown-Timer, Minecraft-Server-Status.

- /event erstellen <titel> <datum> <uhrzeit> [beschreibung]  -- kündigt ein Event an, das
  automatisch zum Zeitpunkt gepostet wird (SERVER_ADMIN)
- /event liste                                                 -- zeigt anstehende Events
- /event entfernen <id>                                         -- entfernt ein Event (SERVER_ADMIN)
- /timer <minuten> [nachricht]                                    -- einfacher Countdown-Timer,
  meldet sich im selben Kanal, wenn die Zeit um ist
- /mcstatus <ip>                                                    -- zeigt den Online-Status
  eines Minecraft-Servers (öffentliche API, keine eigene Server-Verwaltung)
"""
import asyncio
import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, error_embed, base_embed
from bot.utils.db_helpers import (
    get_guild_language,
    create_scheduled_event,
    get_upcoming_events,
    get_due_events,
    mark_event_announced,
    remove_scheduled_event,
)


class EventsMisc(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self._event_check_loop.start()

    def cog_unload(self) -> None:
        self._event_check_loop.cancel()

    @tasks.loop(minutes=1)
    async def _event_check_loop(self) -> None:
        due = await get_due_events(dt.datetime.utcnow())
        for event in due:
            guild = self.bot.get_guild(event.guild_id)
            if not guild:
                await mark_event_announced(event.id)
                continue
            channel = guild.get_channel(event.channel_id)
            if channel:
                embed = base_embed(f"📅 {event.title}", event.description or "")
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass
            await mark_event_announced(event.id)

    @_event_check_loop.before_loop
    async def _before_event_check(self) -> None:
        await self.bot.wait_until_ready()

    @commands.hybrid_group(name="event", description="Event-Ankündigungen verwalten.")
    @commands.guild_only()
    async def event(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @event.command(name="erstellen", description="Kündigt ein Event an, das automatisch gepostet wird.")
    @app_commands.describe(
        titel="Titel des Events", datum="Datum im Format TT.MM.JJJJ", uhrzeit="Uhrzeit im Format HH:MM (UTC)",
        beschreibung="Optionale Beschreibung",
    )
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def event_erstellen(self, ctx: commands.Context, titel: str, datum: str, uhrzeit: str, *, beschreibung: str = ""):
        lang = await get_guild_language(ctx.guild.id)
        try:
            event_time = dt.datetime.strptime(f"{datum} {uhrzeit}", "%d.%m.%Y %H:%M")
        except ValueError:
            await ctx.send(embed=error_embed(
                "Ungültiges Format. Datum: TT.MM.JJJJ, Uhrzeit: HH:MM." if lang == "de"
                else "Invalid format. Date: DD.MM.YYYY, time: HH:MM."))
            return

        event = await create_scheduled_event(ctx.guild.id, ctx.channel.id, titel, beschreibung, event_time, ctx.author.id)
        await ctx.send(embed=success_embed(
            f"📅 Event #{event.id} wird am {datum} um {uhrzeit} UTC in diesem Kanal angekündigt." if lang == "de"
            else f"📅 Event #{event.id} will be announced on {datum} at {uhrzeit} UTC in this channel."))

    @event.command(name="liste", description="Zeigt anstehende Events.")
    async def event_liste(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        events = await get_upcoming_events(ctx.guild.id)
        if not events:
            await ctx.send(embed=error_embed("Keine anstehenden Events." if lang == "de" else "No upcoming events."))
            return
        lines = [f"#{e.id} — **{e.title}** — {e.event_time.strftime('%d.%m.%Y %H:%M')} UTC" for e in events]
        await ctx.send(embed=base_embed("📅 Anstehende Events", "\n".join(lines)))

    @event.command(name="entfernen", description="Entfernt ein Event.")
    @app_commands.describe(event_id="Die ID aus /event liste")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def event_entfernen(self, ctx: commands.Context, event_id: int):
        ok = await remove_scheduled_event(event_id)
        await ctx.send(embed=success_embed("Entfernt.") if ok else error_embed("ID nicht gefunden."))

    @commands.hybrid_command(name="timer", description="Startet einen Countdown-Timer.")
    @app_commands.describe(minuten="Dauer in Minuten (1-1440)", nachricht="Optionale Nachricht, wenn die Zeit um ist")
    @commands.guild_only()
    async def timer(self, ctx: commands.Context, minuten: int, *, nachricht: str = ""):
        lang = await get_guild_language(ctx.guild.id)
        if minuten < 1 or minuten > 1440:
            await ctx.send(embed=error_embed(
                "Die Dauer muss zwischen 1 und 1440 Minuten liegen." if lang == "de"
                else "Duration must be between 1 and 1440 minutes."), ephemeral=True)
            return

        await ctx.send(embed=success_embed(
            f"⏱️ Timer gestartet: {minuten} Minute(n)." if lang == "de" else f"⏱️ Timer started: {minuten} minute(s)."))

        async def _run_timer():
            await asyncio.sleep(minuten * 60)
            text = f"⏰ {ctx.author.mention} " + (
                f"Zeit ist um! {nachricht}" if lang == "de" else f"Time's up! {nachricht}"
            )
            try:
                await ctx.channel.send(text.strip())
            except discord.Forbidden:
                pass

        self.bot.loop.create_task(_run_timer())

    @commands.hybrid_command(name="mcstatus", description="Zeigt den Online-Status eines Minecraft-Servers.")
    @app_commands.describe(ip="Die Server-Adresse, z.B. mc.hypixel.net")
    async def mcstatus(self, ctx: commands.Context, ip: str):
        lang = await get_guild_language(ctx.guild.id) if ctx.guild else "de"
        await ctx.defer()
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://api.mcsrvstat.us/3/{ip}", timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        raise ValueError("API nicht erreichbar")
                    data = await resp.json()
        except Exception:
            await ctx.send(embed=error_embed(
                "Server-Status konnte nicht abgerufen werden." if lang == "de"
                else "Couldn't fetch server status."))
            return

        if not data.get("online"):
            await ctx.send(embed=error_embed(f"🔴 {ip} ist offline oder nicht erreichbar."))
            return

        players = data.get("players", {})
        embed = success_embed(f"🟢 {ip}")
        embed.add_field(name="Spieler" if lang == "de" else "Players",
                         value=f"{players.get('online', '?')}/{players.get('max', '?')}", inline=True)
        if data.get("version"):
            embed.add_field(name="Version", value=str(data["version"]), inline=True)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(EventsMisc(bot))
