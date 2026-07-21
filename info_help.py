"""
Moderations-Befehle: kick, ban, unban, timeout, warn, clear.

Alle Befehle sind Hybrid-Commands -> funktionieren als /befehl und !befehl.
Berechtigung: mindestens MODERATOR (siehe bot/utils/permissions.py).

Bei kick/ban/timeout/warn ist reason PFLICHT (kein Standardwert mehr) --
das Strafregister (siehe bot/cogs/strafregister.py) soll immer einen echten
Grund zeigen, nie nur "Kein Grund angegeben".
"""
import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, error_embed
from bot.utils.i18n import t
from bot.utils.time_parser import parse_duration, InvalidDurationError
from bot.utils.db_helpers import (
    get_guild_language,
    log_punishment,
    get_user_punishments,
    deactivate_punishment,
)


def _hierarchy_ok(actor: discord.Member, target: discord.Member) -> bool:
    """Verhindert, dass jemand einen gleich- oder höherrangigen moderiert (außer Server-Owner)."""
    if actor.id == actor.guild.owner_id:
        return True
    return actor.top_role > target.top_role


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- KICK ----------
    @commands.hybrid_command(name="kick", description="Kickt ein Mitglied vom Server.")
    @app_commands.describe(member="Das zu kickende Mitglied", reason="Grund für den Kick")
    @commands.guild_only()
    @require_level(PermissionLevel.MODERATOR)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str):
        lang = await get_guild_language(ctx.guild.id)

        if member.id == ctx.author.id:
            await ctx.send(embed=error_embed(t("moderation.cannot_moderate_self", lang)), ephemeral=True)
            return
        if not _hierarchy_ok(ctx.author, member):
            await ctx.send(embed=error_embed(t("moderation.cannot_moderate_higher", lang)), ephemeral=True)
            return

        try:
            await member.send(f"Du wurdest von **{ctx.guild.name}** gekickt. Grund: {reason}")
        except discord.Forbidden:
            pass  # DMs geschlossen — kein Blocker

        await member.kick(reason=f"{reason} | Moderator: {ctx.author}")
        await log_punishment(ctx.guild.id, member.id, ctx.author.id, "kick", reason)
        await ctx.send(embed=success_embed(t("moderation.kick_success", lang, user=member.mention)))

    # ---------- BAN ----------
    @commands.hybrid_command(name="ban", description="Bannt ein Mitglied vom Server.")
    @app_commands.describe(member="Das zu bannende Mitglied", reason="Grund für den Bann")
    @commands.guild_only()
    @require_level(PermissionLevel.MODERATOR)
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: str):
        lang = await get_guild_language(ctx.guild.id)

        if member.id == ctx.author.id:
            await ctx.send(embed=error_embed(t("moderation.cannot_moderate_self", lang)), ephemeral=True)
            return
        if not _hierarchy_ok(ctx.author, member):
            await ctx.send(embed=error_embed(t("moderation.cannot_moderate_higher", lang)), ephemeral=True)
            return

        try:
            await member.send(f"Du wurdest von **{ctx.guild.name}** gebannt. Grund: {reason}")
        except discord.Forbidden:
            pass

        await member.ban(reason=f"{reason} | Moderator: {ctx.author}")
        await log_punishment(ctx.guild.id, member.id, ctx.author.id, "ban", reason)
        await ctx.send(embed=success_embed(t("moderation.ban_success", lang, user=member.mention)))

    # ---------- UNBAN ----------
    @commands.hybrid_command(name="unban", description="Hebt einen Bann auf (User-ID erforderlich).")
    @app_commands.describe(user_id="Die Discord-User-ID der Person")
    @commands.guild_only()
    @require_level(PermissionLevel.MODERATOR)
    async def unban(self, ctx: commands.Context, user_id: str):
        lang = await get_guild_language(ctx.guild.id)
        try:
            uid = int(user_id)
        except ValueError:
            await ctx.send(embed=error_embed("Ungültige User-ID" if lang == "de" else "Invalid user ID"))
            return

        try:
            await ctx.guild.unban(discord.Object(id=uid), reason=f"Entbannt von {ctx.author}")
        except discord.NotFound:
            await ctx.send(embed=error_embed("Diese Person ist nicht gebannt." if lang == "de"
                                              else "That user is not banned."))
            return

        await ctx.send(embed=success_embed(t("moderation.unban_success", lang, user_id=uid)))

    # ---------- TIMEOUT ----------
    @commands.hybrid_command(name="timeout", description="Setzt ein Mitglied für eine bestimmte Dauer in Timeout.")
    @app_commands.describe(member="Das Mitglied", duration="z.B. 10m, 1h, 1d", reason="Grund")
    @commands.guild_only()
    @require_level(PermissionLevel.MODERATOR)
    async def timeout(self, ctx: commands.Context, member: discord.Member, duration: str,
                       *, reason: str):
        lang = await get_guild_language(ctx.guild.id)

        if member.id == ctx.author.id:
            await ctx.send(embed=error_embed(t("moderation.cannot_moderate_self", lang)), ephemeral=True)
            return
        if not _hierarchy_ok(ctx.author, member):
            await ctx.send(embed=error_embed(t("moderation.cannot_moderate_higher", lang)), ephemeral=True)
            return

        try:
            delta = parse_duration(duration)
        except InvalidDurationError as e:
            await ctx.send(embed=error_embed(str(e)), ephemeral=True)
            return

        await member.timeout(delta, reason=f"{reason} | Moderator: {ctx.author}")
        await log_punishment(ctx.guild.id, member.id, ctx.author.id, "timeout", reason)
        await ctx.send(embed=success_embed(
            t("moderation.timeout_success", lang, user=member.mention, duration=duration)))

    # ---------- WARN (Gruppe: add / list / remove) ----------
    @commands.hybrid_group(name="warn", description="Verwarnungssystem: add / list / remove")
    @commands.guild_only()
    async def warn(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @warn.command(name="add", description="Fügt einem Mitglied eine Verwarnung hinzu.")
    @app_commands.describe(member="Das Mitglied", reason="Grund der Verwarnung")
    @require_level(PermissionLevel.MODERATOR)
    async def warn_add(self, ctx: commands.Context, member: discord.Member, *, reason: str):
        lang = await get_guild_language(ctx.guild.id)
        await log_punishment(ctx.guild.id, member.id, ctx.author.id, "warn", reason)
        await ctx.send(embed=success_embed(t("moderation.warn_added", lang, user=member.mention, reason=reason)))

    @warn.command(name="list", description="Zeigt alle aktiven Verwarnungen eines Mitglieds.")
    @app_commands.describe(member="Das Mitglied")
    @require_level(PermissionLevel.MODERATOR)
    async def warn_list(self, ctx: commands.Context, member: discord.Member):
        lang = await get_guild_language(ctx.guild.id)
        warnings = [p for p in await get_user_punishments(ctx.guild.id, member.id) if p.type == "warn"]

        if not warnings:
            await ctx.send(embed=success_embed(t("moderation.warn_none", lang, user=member.mention)))
            return

        embed = success_embed(t("moderation.warn_list_title", lang, user=member.display_name))
        embed.color = discord.Color.orange()
        for w in warnings[:25]:  # Discord-Embed-Feld-Limit
            embed.add_field(
                name=f"#{w.id} — {w.created_at.strftime('%d.%m.%Y %H:%M')}",
                value=f"Grund: {w.reason}\nModerator: <@{w.moderator_id}>",
                inline=False,
            )
        await ctx.send(embed=embed)

    @warn.command(name="remove", description="Entfernt eine Verwarnung anhand ihrer ID.")
    @app_commands.describe(warning_id="Die ID der Verwarnung (aus /warn list)")
    @require_level(PermissionLevel.MODERATOR)
    async def warn_remove(self, ctx: commands.Context, warning_id: int):
        lang = await get_guild_language(ctx.guild.id)
        ok = await deactivate_punishment(warning_id)
        if not ok:
            await ctx.send(embed=error_embed("Diese Verwarnungs-ID wurde nicht gefunden." if lang == "de"
                                              else "That warning ID was not found."))
            return
        await ctx.send(embed=success_embed(t("moderation.warn_removed", lang, id=warning_id)))

    # ---------- CLEAR ----------
    @commands.hybrid_command(name="clear", description="Löscht mehrere Nachrichten aus dem Kanal (1-1000).")
    @app_commands.describe(anzahl="Wie viele Nachrichten gelöscht werden sollen (1-1000)")
    @commands.guild_only()
    @require_level(PermissionLevel.MODERATOR)
    async def clear(self, ctx: commands.Context, anzahl: int):
        lang = await get_guild_language(ctx.guild.id)

        if anzahl < 1 or anzahl > 1000:
            await ctx.send(embed=error_embed(
                "Die Anzahl muss zwischen 1 und 1000 liegen." if lang == "de"
                else "The amount must be between 1 and 1000."), ephemeral=True)
            return

        # Bei größeren Mengen kann das Löschen (v.a. wegen Rate-Limits und
        # eventuell nötiger Einzel-Löschung für Nachrichten älter als 14 Tage)
        # länger als 3 Sekunden dauern -> defer() nicht vergessen.
        await ctx.defer(ephemeral=True)

        try:
            deleted = await ctx.channel.purge(limit=anzahl)
        except discord.Forbidden:
            await ctx.send(embed=error_embed(
                "Mir fehlt die Berechtigung 'Nachrichten verwalten' in diesem Kanal." if lang == "de"
                else "I'm missing the 'Manage Messages' permission in this channel."), ephemeral=True)
            return
        except discord.HTTPException as e:
            await ctx.send(embed=error_embed(
                f"Fehler beim Löschen: {e}" if lang == "de" else f"Error while deleting: {e}"), ephemeral=True)
            return

        if len(deleted) < anzahl:
            extra_note = (
                " (Der Rest waren vermutlich Nachrichten älter als 14 Tage — die kann Discord nicht "
                "bulk-löschen — oder es gab im Kanal nicht mehr Nachrichten.)" if lang == "de" else
                " (The rest were likely messages older than 14 days — Discord can't bulk-delete those — "
                "or the channel simply didn't have more messages.)"
            )
        else:
            extra_note = ""
        summary = (
            f"{len(deleted)} von {anzahl} angeforderten Nachrichten gelöscht.{extra_note}" if lang == "de"
            else f"{len(deleted)} of {anzahl} requested messages deleted.{extra_note}"
        )
        await ctx.send(embed=success_embed(
            "Nachrichten gelöscht" if lang == "de" else "Messages cleared", summary,
        ), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
