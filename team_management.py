"""
Strafregister-System.

- /strafregister <user>                    -- zeigt ALLE Strafen eines Users (Team/Moderator/Admin
                                               ODER eine per /strafregister_recht_geben freigeschaltete Rolle)
- /strafregister_recht_geben <rolle>       -- gibt einer Rolle Einsicht ins Strafregister (SERVER_ADMIN)
- /strafregister_recht_entfernen <rolle>   -- entzieht einer Rolle die Einsicht (SERVER_ADMIN)
- /strafregister_rechte                    -- zeigt, welche Rollen zusätzlich Einsicht haben

Nutzt dieselbe Punishment-Tabelle, die schon von /kick, /ban, /timeout, /warn,
Anti-Nuke, Anti-Spam, Anti-Hack und Anti-Werbung befüllt wird -- das
Strafregister ist also automatisch vollständig, ohne doppelte Datenhaltung.
Seit dieser Version ist bei JEDER Strafe ein Grund PFLICHT (siehe moderation.py
und team_management.py), damit das Strafregister immer aussagekräftig bleibt.
"""
import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.permissions import require_level, PermissionLevel, get_member_permission_level
from bot.utils.embeds import success_embed, error_embed, base_embed
from bot.utils.i18n import t
from bot.utils.db_helpers import (
    get_guild_language,
    get_user_punishments,
    grant_register_access,
    revoke_register_access,
    get_register_access_roles,
)

# Menschenlesbare Labels für die Strafentypen im Register (technische
# type-Strings aus der Punishment-Tabelle -> Anzeigename).
TYPE_LABELS = {
    "kick": "Kick",
    "ban": "Ban",
    "timeout": "Timeout",
    "warn": "Verwarnung",
    "team_warn": "Team-Verwarnung",
    "team_kick": "Team-Kick",
    "anti_nuke_action": "Anti-Nuke",
    "anti_spam_timeout": "Anti-Spam",
    "anti_hack_kick": "Anti-Hack",
    "anti_werbung_timeout": "Anti-Werbung (Timeout)",
    "anti_werbung_kick": "Anti-Werbung (Kick)",
}


async def _has_register_access(member: discord.Member) -> bool:
    if get_member_permission_level(member) >= PermissionLevel.TEAM:
        return True
    access_roles = {r.role_id for r in await get_register_access_roles(member.guild.id)}
    return any(role.id in access_roles for role in member.roles)


class Strafregister(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="strafregister", description="Zeigt das vollständige Strafregister eines Users.")
    @app_commands.describe(member="Das Mitglied")
    @commands.guild_only()
    async def strafregister(self, ctx: commands.Context, member: discord.Member):
        lang = await get_guild_language(ctx.guild.id)

        if not isinstance(ctx.author, discord.Member) or not await _has_register_access(ctx.author):
            await ctx.send(embed=error_embed(t("strafregister.no_access", lang)), ephemeral=True)
            return

        entries = await get_user_punishments(ctx.guild.id, member.id, active_only=False)
        if not entries:
            await ctx.send(embed=error_embed(t("strafregister.empty", lang, user=member.display_name)))
            return

        embed = base_embed(t("strafregister.title", lang, user=member.display_name))
        embed.set_thumbnail(url=member.display_avatar.url)
        for entry in entries[:25]:  # Discord-Embed-Feld-Limit
            label = TYPE_LABELS.get(entry.type, entry.type)
            status = "" if entry.active else (" (aufgehoben)" if lang == "de" else " (revoked)")
            embed.add_field(
                name=f"#{entry.id} — {label}{status} — {entry.created_at.strftime('%d.%m.%Y %H:%M')}",
                value=f"Grund: {entry.reason}\nModerator: <@{entry.moderator_id}>" if lang == "de"
                else f"Reason: {entry.reason}\nModerator: <@{entry.moderator_id}>",
                inline=False,
            )
        embed.set_footer(text=f"{len(entries)} Einträge insgesamt" if lang == "de"
                          else f"{len(entries)} entries total")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="strafregister_recht_geben",
                              description="Gibt einer Rolle Einsicht ins Strafregister.")
    @app_commands.describe(rolle="Die Rolle, die Einsicht bekommen soll")
    @commands.guild_only()
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def strafregister_recht_geben(self, ctx: commands.Context, rolle: discord.Role):
        lang = await get_guild_language(ctx.guild.id)
        granted = await grant_register_access(ctx.guild.id, rolle.id, ctx.author.id)
        if granted:
            await ctx.send(embed=success_embed(t("strafregister.access_granted", lang, role=rolle.mention)))
        else:
            await ctx.send(embed=error_embed(t("strafregister.access_already", lang, role=rolle.mention)))

    @commands.hybrid_command(name="strafregister_recht_entfernen",
                              description="Entzieht einer Rolle die Einsicht ins Strafregister.")
    @app_commands.describe(rolle="Die Rolle, der die Einsicht entzogen wird")
    @commands.guild_only()
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def strafregister_recht_entfernen(self, ctx: commands.Context, rolle: discord.Role):
        lang = await get_guild_language(ctx.guild.id)
        revoked = await revoke_register_access(ctx.guild.id, rolle.id)
        if revoked:
            await ctx.send(embed=success_embed(t("strafregister.access_revoked", lang, role=rolle.mention)))
        else:
            await ctx.send(embed=error_embed(t("strafregister.access_not_found", lang, role=rolle.mention)))

    @commands.hybrid_command(name="strafregister_rechte",
                              description="Zeigt, welche Rollen zusätzlich Einsicht ins Strafregister haben.")
    @commands.guild_only()
    async def strafregister_rechte(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        roles = await get_register_access_roles(ctx.guild.id)
        if not roles:
            await ctx.send(embed=error_embed(t("strafregister.access_list_empty", lang)))
            return

        embed = base_embed(t("strafregister.access_list_title", lang))
        lines = [f"<@&{r.role_id}>" for r in roles]
        embed.description = "\n".join(lines)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Strafregister(bot))
