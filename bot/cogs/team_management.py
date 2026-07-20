"""
Team-Management: Rang-Hierarchie einrichten, Uprank/Downrank, Teamkick, Teamliste.

Setup (/teamrank add) darf nur SERVER_ADMIN.
Uprank/Downrank/Teamkick dürfen MODERATOR (anpassbar später übers Dashboard).
"""
import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, error_embed, base_embed
from bot.utils.i18n import t
from bot.utils.db_helpers import (
    get_guild_language,
    get_team_ranks,
    get_team_member,
    get_all_team_members,
    upsert_team_member,
    remove_team_member,
    log_punishment,
)
from bot.database.db import get_session
from bot.database.models import TeamRank


class TeamManagement(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- TEAMRANK (Setup-Gruppe) ----------
    @commands.hybrid_group(name="teamrank", description="Team-Rang-Hierarchie einrichten (nur Server-Admin).")
    @commands.guild_only()
    async def teamrank(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @teamrank.command(name="add", description="Fügt eine Rolle als Team-Rang hinzu (am Ende der Hierarchie).")
    @app_commands.describe(role="Die Discord-Rolle, die als Team-Rang gelten soll")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def teamrank_add(self, ctx: commands.Context, role: discord.Role):
        lang = await get_guild_language(ctx.guild.id)
        existing = await get_team_ranks(ctx.guild.id)
        next_position = max((r.position for r in existing), default=-1) + 1

        async with get_session() as session:
            session.add(TeamRank(guild_id=ctx.guild.id, role_id=role.id, position=next_position))
            await session.commit()

        await ctx.send(embed=success_embed(t("team.rank_added", lang, role=role.mention, position=next_position)))

    @teamrank.command(name="list", description="Zeigt die Team-Rang-Hierarchie (niedrig -> hoch).")
    async def teamrank_list(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        ranks = await get_team_ranks(ctx.guild.id)
        if not ranks:
            await ctx.send(embed=error_embed(t("team.rank_none", lang)))
            return

        embed = base_embed(t("team.rank_list_title", lang))
        lines = []
        for rank in ranks:
            role = ctx.guild.get_role(rank.role_id)
            role_display = role.mention if role else f"(gelöschte Rolle: {rank.role_id})"
            lines.append(f"**{rank.position}.** {role_display}")
        embed.description = "\n".join(lines)
        await ctx.send(embed=embed)

    @teamrank.command(name="remove", description="Entfernt eine Rolle aus der Team-Rang-Hierarchie.")
    @app_commands.describe(role="Die zu entfernende Team-Rang-Rolle")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def teamrank_remove(self, ctx: commands.Context, role: discord.Role):
        lang = await get_guild_language(ctx.guild.id)
        async with get_session() as session:
            ranks = await get_team_ranks(ctx.guild.id)
            match = next((r for r in ranks if r.role_id == role.id), None)
            if match is None:
                await ctx.send(embed=error_embed("Diese Rolle ist kein Team-Rang." if lang == "de"
                                                  else "That role is not a team rank."))
                return
            obj = await session.get(TeamRank, match.id)
            await session.delete(obj)
            await session.commit()
        await ctx.send(embed=success_embed(t("team.rank_removed", lang)))

    # ---------- UPRANK ----------
    @commands.hybrid_command(name="uprank", description="Befördert ein Teammitglied zum nächsthöheren Rang.")
    @app_commands.describe(member="Das Teammitglied")
    @commands.guild_only()
    @require_level(PermissionLevel.MODERATOR)
    async def uprank(self, ctx: commands.Context, member: discord.Member):
        lang = await get_guild_language(ctx.guild.id)
        ranks = await get_team_ranks(ctx.guild.id)
        if not ranks:
            await ctx.send(embed=error_embed(t("team.rank_none", lang)))
            return

        team_member = await get_team_member(ctx.guild.id, member.id)
        current_position = -1
        if team_member and team_member.current_rank_id:
            current = next((r for r in ranks if r.id == team_member.current_rank_id), None)
            if current:
                current_position = current.position

        next_rank = next((r for r in ranks if r.position == current_position + 1), None)
        if next_rank is None:
            await ctx.send(embed=error_embed(t("team.uprank_already_top", lang, user=member.mention)))
            return

        new_role = ctx.guild.get_role(next_rank.role_id)
        old_role = None
        if team_member and team_member.current_rank_id:
            old_rank = next((r for r in ranks if r.id == team_member.current_rank_id), None)
            old_role = ctx.guild.get_role(old_rank.role_id) if old_rank else None

        if new_role:
            await member.add_roles(new_role, reason=f"Uprank durch {ctx.author}")
        if old_role and old_role in member.roles:
            await member.remove_roles(old_role, reason=f"Uprank durch {ctx.author}")

        await upsert_team_member(ctx.guild.id, member.id, next_rank.id)
        await ctx.send(embed=success_embed(
            t("team.uprank_success", lang, user=member.mention, rank=new_role.name if new_role else "?")))

    # ---------- DOWNRANK ----------
    @commands.hybrid_command(name="downrank", description="Stuft ein Teammitglied einen Rang zurück.")
    @app_commands.describe(member="Das Teammitglied")
    @commands.guild_only()
    @require_level(PermissionLevel.MODERATOR)
    async def downrank(self, ctx: commands.Context, member: discord.Member):
        lang = await get_guild_language(ctx.guild.id)
        ranks = await get_team_ranks(ctx.guild.id)
        team_member = await get_team_member(ctx.guild.id, member.id)

        if not team_member or not team_member.current_rank_id:
            await ctx.send(embed=error_embed(t("team.not_in_team", lang, user=member.mention)))
            return

        current = next((r for r in ranks if r.id == team_member.current_rank_id), None)
        if current is None or current.position == 0:
            await ctx.send(embed=error_embed(t("team.downrank_already_bottom", lang, user=member.mention)))
            return

        prev_rank = next((r for r in ranks if r.position == current.position - 1), None)
        old_role = ctx.guild.get_role(current.role_id)
        new_role = ctx.guild.get_role(prev_rank.role_id) if prev_rank else None

        if old_role and old_role in member.roles:
            await member.remove_roles(old_role, reason=f"Downrank durch {ctx.author}")
        if new_role:
            await member.add_roles(new_role, reason=f"Downrank durch {ctx.author}")

        await upsert_team_member(ctx.guild.id, member.id, prev_rank.id if prev_rank else None)
        await ctx.send(embed=success_embed(
            t("team.downrank_success", lang, user=member.mention, rank=new_role.name if new_role else "—")))

    # ---------- TEAMKICK ----------
    @commands.hybrid_command(name="teamkick", description="Entfernt ein Mitglied aus dem Team (alle Team-Rollen).")
    @app_commands.describe(member="Das Teammitglied", reason="Grund")
    @commands.guild_only()
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def teamkick(self, ctx: commands.Context, member: discord.Member, *, reason: str):
        lang = await get_guild_language(ctx.guild.id)
        ranks = await get_team_ranks(ctx.guild.id)
        team_role_ids = {r.role_id for r in ranks}

        roles_to_remove = [role for role in member.roles if role.id in team_role_ids]
        if roles_to_remove:
            await member.remove_roles(*roles_to_remove, reason=f"Teamkick: {reason} | {ctx.author}")

        await remove_team_member(ctx.guild.id, member.id)
        await log_punishment(ctx.guild.id, member.id, ctx.author.id, "team_kick", reason, is_team_punishment=True)
        await ctx.send(embed=success_embed(t("team.teamkick_success", lang, user=member.mention, reason=reason)))

    # ---------- TEAMLISTE ----------
    @commands.hybrid_command(name="teamliste", description="Zeigt alle aktuellen Teammitglieder mit Rang.")
    @commands.guild_only()
    async def teamliste(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        members = await get_all_team_members(ctx.guild.id)
        ranks = {r.id: r for r in await get_team_ranks(ctx.guild.id)}

        if not members:
            await ctx.send(embed=error_embed(t("team.teamliste_empty", lang)))
            return

        embed = base_embed(t("team.teamliste_title", lang))
        # Nach Rang-Position gruppieren, höchster zuerst
        sorted_members = sorted(
            members,
            key=lambda m: ranks[m.current_rank_id].position if m.current_rank_id in ranks else -1,
            reverse=True,
        )
        lines = []
        for m in sorted_members:
            rank = ranks.get(m.current_rank_id)
            role = ctx.guild.get_role(rank.role_id) if rank else None
            rank_name = role.name if role else "—"
            lines.append(f"<@{m.user_id}> — **{rank_name}**")
        embed.description = "\n".join(lines[:50])  # Discord Embed-Limit im Blick behalten
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(TeamManagement(bot))
