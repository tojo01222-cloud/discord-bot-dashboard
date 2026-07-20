"""
Invite-Tracking.

- /invites [user]        -- zeigt, wie viele echte Einladungen ein User hat
- /inviteleaderboard      -- Top 10 Einlader des Servers
- /invitestats [user]     -- detaillierte Statistik (echt/fake/gesamt) eines Users

Funktionsweise: Discord liefert keinen direkten "dieser Link wurde benutzt"-
Event beim Member-Beitritt. Stattdessen wird bei jedem Beitritt die aktuelle
Nutzungszahl (uses) aller Server-Invites mit dem zuletzt gespeicherten Stand
verglichen -- welcher Invite genau um 1 gestiegen ist, war der benutzte.

Fake-Erkennung (einfache Heuristik, keine Garantie): ein Account, der zum
Zeitpunkt des Beitritts jünger als 7 Tage ist, gilt als potenziell "fake"
und zählt nicht zu den echten Einladungen.
"""
import datetime as dt
import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.embeds import base_embed, error_embed
from bot.utils.db_helpers import (
    get_guild_language,
    get_invite_records,
    upsert_invite_record,
    remove_invite_record,
    record_invite_join,
    get_invite_count,
    get_invite_leaderboard,
    get_invite_stats,
)

log = logging.getLogger("bot.cogs.invites")

FAKE_ACCOUNT_AGE_DAYS = 7


class Invites(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _sync_guild_invites(self, guild: discord.Guild) -> None:
        try:
            invites = await guild.invites()
        except discord.Forbidden:
            log.warning("Fehlende 'Manage Server'-Berechtigung für Invite-Tracking in Guild %s", guild.id)
            return
        for invite in invites:
            inviter_id = invite.inviter.id if invite.inviter else 0
            await upsert_invite_record(guild.id, invite.code, inviter_id, invite.uses or 0)

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            await self._sync_guild_invites(guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await self._sync_guild_invites(guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        inviter_id = invite.inviter.id if invite.inviter else 0
        await upsert_invite_record(invite.guild.id, invite.code, inviter_id, invite.uses or 0)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        await remove_invite_record(invite.code)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        try:
            current_invites = await guild.invites()
        except discord.Forbidden:
            return

        known = await get_invite_records(guild.id)
        used_invite = None
        for invite in current_invites:
            record = known.get(invite.code)
            if record and (invite.uses or 0) > record.uses:
                used_invite = invite
                break

        # Snapshot immer aktualisieren, unabhängig davon, ob wir den genutzten
        # Invite finden konnten (z.B. bei Vanity-URLs, die nicht auftauchen).
        for invite in current_invites:
            inviter_id = invite.inviter.id if invite.inviter else 0
            await upsert_invite_record(guild.id, invite.code, inviter_id, invite.uses or 0)

        if not used_invite or not used_invite.inviter:
            return

        account_age = dt.datetime.now(dt.timezone.utc) - member.created_at
        is_fake = account_age.days < FAKE_ACCOUNT_AGE_DAYS

        await record_invite_join(guild.id, member.id, used_invite.inviter.id, is_fake)

    @commands.hybrid_command(name="invites", description="Zeigt, wie viele echte Einladungen ein User hat.")
    @app_commands.describe(member="Optional: ein anderer User")
    @commands.guild_only()
    async def invites_cmd(self, ctx: commands.Context, member: discord.Member = None):
        target = member or ctx.author
        lang = await get_guild_language(ctx.guild.id)
        count = await get_invite_count(ctx.guild.id, target.id)

        embed = base_embed(f"📨 Einladungen von {target.display_name}" if lang == "de"
                            else f"📨 Invites by {target.display_name}")
        embed.description = (f"**{count}** echte Einladungen" if lang == "de"
                              else f"**{count}** real invites")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="inviteleaderboard", description="Zeigt die Top 10 Einlader des Servers.")
    @commands.guild_only()
    async def inviteleaderboard(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        top = await get_invite_leaderboard(ctx.guild.id, limit=10)
        if not top:
            await ctx.send(embed=error_embed("Noch keine Einladungen erfasst." if lang == "de"
                                              else "No invites tracked yet."))
            return

        embed = base_embed("📨 Invite-Leaderboard" if lang == "de" else "📨 Invite leaderboard")
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, (inviter_id, count) in enumerate(top):
            prefix = medals[i] if i < 3 else f"{i+1}."
            plural = "Einladung" if count == 1 else "Einladungen" if lang == "de" else ("invite" if count == 1 else "invites")
            lines.append(f"{prefix} <@{inviter_id}> — **{count}** {plural}")
        embed.description = "\n".join(lines)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="invitestats", description="Zeigt eine detaillierte Invite-Statistik (echt/fake/gesamt).")
    @app_commands.describe(member="Optional: ein anderer User")
    @commands.guild_only()
    async def invitestats(self, ctx: commands.Context, member: discord.Member = None):
        target = member or ctx.author
        lang = await get_guild_language(ctx.guild.id)
        stats = await get_invite_stats(ctx.guild.id, target.id)

        embed = base_embed(f"📊 Invite-Statistik von {target.display_name}" if lang == "de"
                            else f"📊 Invite stats for {target.display_name}")
        embed.add_field(name="Echt" if lang == "de" else "Real", value=str(stats["real"]), inline=True)
        embed.add_field(name="Fake", value=str(stats["fake"]), inline=True)
        embed.add_field(name="Gesamt" if lang == "de" else "Total", value=str(stats["total"]), inline=True)
        if stats["fake"] > 0:
            embed.set_footer(text=(
                "Fake = Account war bei Beitritt jünger als 7 Tage (Heuristik, keine Garantie)."
                if lang == "de" else
                "Fake = account was younger than 7 days at join (heuristic, not a guarantee)."
            ))
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Invites(bot))
