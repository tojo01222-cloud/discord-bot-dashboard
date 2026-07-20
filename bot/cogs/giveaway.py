"""
Gewinnspiel-System.

/giveaway start <name> <beschreibung> <zeit> <kanal> [gesponsert_von] [invites_benoetigt] [nur_neue_invites]
/giveaway end <id>       -- vorzeitig beenden und auslosen
/giveaway reroll <id>    -- neuen Gewinner auslosen
/giveaway list            -- laufende Gewinnspiele

Zeit-Auswahl: 30s bis 4w, wie gewünscht.
Invites: 1-100 einstellbar, wahlweise "alle bisherigen" oder "nur neue seit
Gewinnspielstart" (siehe use_new_invites_only).

Buttons sind persistent (überleben einen Bot-Neustart) -- werden beim Start
für alle noch laufenden Gewinnspiele neu registriert (siehe cog_load).
"""
import datetime as dt
import logging
import random

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, error_embed, base_embed
from bot.utils.db_helpers import (
    get_guild_language,
    create_giveaway,
    set_giveaway_message_id,
    get_active_giveaways,
    get_giveaways_for_guild,
    get_giveaway,
    end_giveaway,
    add_giveaway_entry,
    get_giveaway_entries,
    get_invite_count,
)

log = logging.getLogger("bot.cogs.giveaway")

TIME_CHOICES = {
    "30s": 30, "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "3h": 10800, "4h": 14400, "5h": 18000, "6h": 21600, "12h": 43200,
    "1d": 86400, "2d": 172800, "3d": 259200, "4d": 345600, "5d": 432000, "6d": 518400,
    "1w": 604800, "2w": 1209600, "3w": 1814400, "4w": 2419200,
}


def _build_giveaway_embed(giveaway, entry_count: int) -> discord.Embed:
    embed = discord.Embed(
        title=f"🎉 {giveaway.name}",
        description=giveaway.description or "Klicke auf den Button, um teilzunehmen!",
        color=discord.Color.gold(),
    )
    embed.add_field(name="Endet", value=discord.utils.format_dt(giveaway.ends_at.replace(tzinfo=dt.timezone.utc), style="R"), inline=True)
    embed.add_field(name="Teilnehmer", value=str(entry_count), inline=True)
    if giveaway.sponsor:
        embed.add_field(name="Gesponsert von", value=giveaway.sponsor, inline=True)
    if giveaway.invites_required > 0:
        scope = "neue Invites seit Start" if giveaway.use_new_invites_only else "Invites insgesamt"
        embed.add_field(name="Voraussetzung", value=f"Mindestens {giveaway.invites_required} {scope}", inline=False)
    if giveaway.ended:
        winner_text = f"<@{giveaway.winner_id}>" if giveaway.winner_id else "Niemand (keine gültige Teilnahme)"
        embed.add_field(name="🏆 Gewinner", value=winner_text, inline=False)
        embed.color = discord.Color.dark_grey()
    return embed


async def _handle_giveaway_join(interaction: discord.Interaction, giveaway_id: int) -> None:
    giveaway = await get_giveaway(giveaway_id)
    lang = await get_guild_language(interaction.guild.id)

    if not giveaway or giveaway.ended:
        await interaction.response.send_message(
            "Dieses Gewinnspiel ist bereits beendet." if lang == "de" else "This giveaway has already ended.",
            ephemeral=True)
        return

    if giveaway.invites_required > 0:
        since = giveaway.started_at if giveaway.use_new_invites_only else None
        count = await get_invite_count(giveaway.guild_id, interaction.user.id, since=since)
        if count < giveaway.invites_required:
            missing = giveaway.invites_required - count
            await interaction.response.send_message(
                (f"Du brauchst mindestens {giveaway.invites_required} Einladungen, um teilzunehmen "
                 f"(du hast aktuell {count}, es fehlen noch {missing}).") if lang == "de" else
                (f"You need at least {giveaway.invites_required} invites to enter "
                 f"(you currently have {count}, {missing} more needed)."),
                ephemeral=True)
            return

    added = await add_giveaway_entry(giveaway_id, interaction.user.id)
    if added:
        await interaction.response.send_message(
            "Du nimmst jetzt teil! 🎉" if lang == "de" else "You're entered! 🎉", ephemeral=True)
    else:
        await interaction.response.send_message(
            "Du nimmst bereits teil." if lang == "de" else "You're already entered.", ephemeral=True)


class GiveawayView(discord.ui.View):
    """Persistenter View mit dynamischem custom_id pro Gewinnspiel (jedes
    Gewinnspiel braucht seinen eigenen Button, daher kein fester custom_id
    wie beim Ticket-System, sondern einer, der die Gewinnspiel-ID enthält)."""

    def __init__(self, giveaway_id: int):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        button = discord.ui.Button(
            label="Teilnehmen", emoji="🎉", style=discord.ButtonStyle.success,
            custom_id=f"giveaway_join_{giveaway_id}",
        )
        button.callback = self._join_callback
        self.add_item(button)

    async def _join_callback(self, interaction: discord.Interaction):
        await _handle_giveaway_join(interaction, self.giveaway_id)


class Giveaway(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        # Persistente Views für alle noch laufenden Gewinnspiele neu registrieren.
        active = await get_active_giveaways()
        for g in active:
            self.bot.add_view(GiveawayView(g.id))
        self._check_expired_giveaways.start()

    def cog_unload(self) -> None:
        self._check_expired_giveaways.cancel()

    @tasks.loop(seconds=30)
    async def _check_expired_giveaways(self) -> None:
        try:
            active = await get_active_giveaways()
            now = dt.datetime.utcnow()
            for g in active:
                if g.ends_at <= now:
                    await self._finish_giveaway(g.id)
        except Exception:
            log.exception("Fehler beim Prüfen abgelaufener Gewinnspiele")

    async def _finish_giveaway(self, giveaway_id: int) -> None:
        giveaway = await get_giveaway(giveaway_id)
        if not giveaway or giveaway.ended:
            return

        entries = await get_giveaway_entries(giveaway_id)
        guild = self.bot.get_guild(giveaway.guild_id)

        # Bevorzugt jemanden auslosen, der den Server nicht inzwischen verlassen
        # hat (Bug-Fix: vorher konnte ein längst ausgetretenes Mitglied gewinnen,
        # dessen Erwähnung dann ins Leere zeigte). Sind ALLE Teilnehmer weg
        # (z.B. sehr alter Giveaway), wird trotzdem ausgelost statt "niemand" zu
        # melden -- das bleibt die bewusste Ausnahme.
        eligible = [e for e in entries if guild and guild.get_member(e.user_id)] if guild else list(entries)
        pool = eligible or entries
        winner_id = random.choice(pool).user_id if pool else 0
        await end_giveaway(giveaway_id, winner_id)

        if not guild:
            return
        channel = guild.get_channel(giveaway.channel_id)
        if not channel:
            return

        giveaway = await get_giveaway(giveaway_id)  # frisch mit ended=True/winner_id laden
        embed = _build_giveaway_embed(giveaway, len(entries))

        try:
            if giveaway.message_id:
                try:
                    message = await channel.fetch_message(giveaway.message_id)
                    await message.edit(embed=embed, view=None)
                except discord.NotFound:
                    pass
            if winner_id:
                await channel.send(f"🎉 Herzlichen Glückwunsch <@{winner_id}>! Du hast **{giveaway.name}** gewonnen!")
            else:
                await channel.send(f"Das Gewinnspiel **{giveaway.name}** ist beendet, aber es gab keine Teilnehmer.")
        except discord.Forbidden:
            pass

    @commands.hybrid_group(name="giveaway", description="Gewinnspiele verwalten.")
    @commands.guild_only()
    async def giveaway(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @giveaway.command(name="start", description="Startet ein neues Gewinnspiel.")
    @app_commands.describe(
        name="Name des Gewinnspiels", beschreibung="Beschreibung/Preis", zeit="Wie lange das Gewinnspiel läuft",
        kanal="In welchem Kanal das Gewinnspiel gepostet wird", gesponsert_von="Optional: Sponsor-Name",
        invites_benoetigt="0-100, wie viele Einladungen zur Teilnahme nötig sind (0 = keine Anforderung)",
        nur_neue_invites="Nur Invites seit Gewinnspielstart zählen (statt aller bisherigen)?",
    )
    @app_commands.choices(zeit=[app_commands.Choice(name=k, value=k) for k in TIME_CHOICES.keys()])
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def giveaway_start(
        self, ctx: commands.Context, name: str, beschreibung: str, zeit: str, kanal: discord.TextChannel,
        gesponsert_von: str = "", invites_benoetigt: int = 0, nur_neue_invites: bool = True,
    ):
        lang = await get_guild_language(ctx.guild.id)

        if zeit not in TIME_CHOICES:
            await ctx.send(embed=error_embed("Ungültige Zeitauswahl." if lang == "de" else "Invalid time choice."))
            return
        if invites_benoetigt < 0 or invites_benoetigt > 100:
            await ctx.send(embed=error_embed(
                "invites_benoetigt muss zwischen 0 und 100 liegen." if lang == "de"
                else "invites_benoetigt must be between 0 and 100."))
            return

        await ctx.defer()

        ends_at = dt.datetime.utcnow() + dt.timedelta(seconds=TIME_CHOICES[zeit])
        giveaway = await create_giveaway(
            ctx.guild.id, kanal.id, name, beschreibung, gesponsert_von,
            invites_benoetigt, nur_neue_invites, ctx.author.id, ends_at,
        )

        embed = _build_giveaway_embed(giveaway, 0)
        view = GiveawayView(giveaway.id)
        message = await kanal.send(embed=embed, view=view)
        await set_giveaway_message_id(giveaway.id, message.id)

        await ctx.send(embed=success_embed(
            "Gewinnspiel gestartet" if lang == "de" else "Giveaway started",
            f"In {kanal.mention}, endet in {zeit}.",
        ))

    @giveaway.command(name="end", description="Beendet ein Gewinnspiel sofort und lost aus.")
    @app_commands.describe(giveaway_id="Die ID des Gewinnspiels (siehe /giveaway list)")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def giveaway_end(self, ctx: commands.Context, giveaway_id: int):
        lang = await get_guild_language(ctx.guild.id)
        giveaway = await get_giveaway(giveaway_id)
        if not giveaway or giveaway.guild_id != ctx.guild.id:
            await ctx.send(embed=error_embed("Gewinnspiel nicht gefunden." if lang == "de" else "Giveaway not found."))
            return
        if giveaway.ended:
            await ctx.send(embed=error_embed("Ist bereits beendet." if lang == "de" else "Already ended."))
            return

        await ctx.defer()
        await self._finish_giveaway(giveaway_id)
        await ctx.send(embed=success_embed("Beendet und ausgelost." if lang == "de" else "Ended and drawn."))

    @giveaway.command(name="reroll", description="Lost einen neuen Gewinner für ein beendetes Gewinnspiel aus.")
    @app_commands.describe(giveaway_id="Die ID des Gewinnspiels")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def giveaway_reroll(self, ctx: commands.Context, giveaway_id: int):
        lang = await get_guild_language(ctx.guild.id)
        giveaway = await get_giveaway(giveaway_id)
        if not giveaway or giveaway.guild_id != ctx.guild.id or not giveaway.ended:
            await ctx.send(embed=error_embed(
                "Kein beendetes Gewinnspiel mit dieser ID gefunden." if lang == "de"
                else "No ended giveaway found with that ID."))
            return

        entries = await get_giveaway_entries(giveaway_id)
        if not entries:
            await ctx.send(embed=error_embed("Keine Teilnehmer vorhanden." if lang == "de" else "No entries."))
            return

        new_winner = random.choice(entries).user_id
        await end_giveaway(giveaway_id, new_winner)
        await ctx.send(embed=success_embed(
            "Neu ausgelost" if lang == "de" else "Rerolled",
            f"🎉 Neuer Gewinner: <@{new_winner}>",
        ))

    @giveaway.command(name="list", description="Zeigt alle laufenden Gewinnspiele.")
    async def giveaway_list(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        all_giveaways = await get_giveaways_for_guild(ctx.guild.id)
        active = [g for g in all_giveaways if not g.ended]

        if not active:
            await ctx.send(embed=error_embed("Keine laufenden Gewinnspiele." if lang == "de"
                                              else "No active giveaways."))
            return

        embed = base_embed("🎉 Laufende Gewinnspiele" if lang == "de" else "🎉 Active giveaways")
        lines = [f"#{g.id} — **{g.name}** (endet {discord.utils.format_dt(g.ends_at.replace(tzinfo=dt.timezone.utc), style='R')})"
                 for g in active]
        embed.description = "\n".join(lines)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaway(bot))
