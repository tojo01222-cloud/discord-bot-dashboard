"""
Reaction-Roles.

- /reactionrole add <nachricht_id> <emoji> <rolle>   -- verknüpft ein Emoji auf einer
                                                          bestehenden Nachricht mit einer Rolle (SERVER_ADMIN)
- /reactionrole remove <id>                            -- entfernt eine Verknüpfung (SERVER_ADMIN)
- /reactionrole list                                    -- zeigt alle eingerichteten Reaction-Roles

Funktionsweise: Der Bot reagiert selbst mit dem Emoji auf die Ziel-Nachricht
(damit User nur noch draufklicken müssen) und hört danach per
on_raw_reaction_add/remove auf Klicks -- funktioniert auch nach einem
Bot-Neustart und bei Nachrichten, die schon vor der Einrichtung existierten.
"""
import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, error_embed, base_embed
from bot.utils.db_helpers import (
    get_guild_language,
    add_reaction_role,
    get_reaction_roles_for_message,
    get_reaction_roles,
    remove_reaction_role,
)


class ReactionRoles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_group(name="reactionrole", description="Reaction-Roles verwalten.")
    @commands.guild_only()
    async def reactionrole(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @reactionrole.command(name="add", description="Verknüpft ein Emoji auf einer Nachricht mit einer Rolle.")
    @app_commands.describe(
        nachricht_id="Die ID der Nachricht (Rechtsklick -> ID kopieren, Entwicklermodus nötig)",
        emoji="Das Emoji (Standard-Emoji oder Server-Emoji)",
        rolle="Die zu vergebende Rolle",
    )
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def reactionrole_add(self, ctx: commands.Context, nachricht_id: str, emoji: str, rolle: discord.Role):
        lang = await get_guild_language(ctx.guild.id)

        if rolle >= ctx.guild.me.top_role:
            await ctx.send(embed=error_embed(
                "Diese Rolle steht höher als (oder gleich) meine eigene." if lang == "de"
                else "That role is higher than (or equal to) my own."))
            return

        try:
            msg_id = int(nachricht_id)
        except ValueError:
            await ctx.send(embed=error_embed("Ungültige Nachrichten-ID." if lang == "de" else "Invalid message ID."))
            return

        try:
            message = await ctx.channel.fetch_message(msg_id)
        except discord.NotFound:
            await ctx.send(embed=error_embed(
                "Nachricht nicht gefunden -- führe den Befehl im selben Kanal wie die Nachricht aus."
                if lang == "de" else
                "Message not found -- run the command in the same channel as the message."))
            return

        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            await ctx.send(embed=error_embed(
                "Ungültiges Emoji oder ich habe keinen Zugriff darauf." if lang == "de"
                else "Invalid emoji or I don't have access to it."))
            return

        await add_reaction_role(ctx.guild.id, msg_id, ctx.channel.id, emoji, rolle.id)
        await ctx.send(embed=success_embed(
            f"Reaction-Role eingerichtet: {emoji} -> {rolle.mention}" if lang == "de"
            else f"Reaction role set up: {emoji} -> {rolle.mention}"))

    @reactionrole.command(name="list", description="Zeigt alle eingerichteten Reaction-Roles.")
    async def reactionrole_list(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        entries = await get_reaction_roles(ctx.guild.id)
        if not entries:
            await ctx.send(embed=error_embed(
                "Keine Reaction-Roles eingerichtet." if lang == "de" else "No reaction roles configured."))
            return

        embed = base_embed("🎭 Reaction-Roles")
        embed.description = "\n".join(
            f"#{e.id} — {e.emoji} -> <@&{e.role_id}> (Nachricht {e.message_id})" for e in entries[:25]
        )
        await ctx.send(embed=embed)

    @reactionrole.command(name="remove", description="Entfernt eine Reaction-Role-Verknüpfung.")
    @app_commands.describe(entry_id="Die ID aus /reactionrole list")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def reactionrole_remove(self, ctx: commands.Context, entry_id: int):
        lang = await get_guild_language(ctx.guild.id)
        ok = await remove_reaction_role(entry_id)
        if ok:
            await ctx.send(embed=success_embed("Entfernt." if lang == "de" else "Removed."))
        else:
            await ctx.send(embed=error_embed("ID nicht gefunden." if lang == "de" else "ID not found."))

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.member is None or payload.member.bot:
            return
        entries = await get_reaction_roles_for_message(payload.message_id)
        if not entries:
            return
        emoji_str = str(payload.emoji)
        for entry in entries:
            if entry.emoji == emoji_str:
                role = payload.member.guild.get_role(entry.role_id)
                if role:
                    try:
                        await payload.member.add_roles(role, reason="Reaction-Role")
                    except discord.Forbidden:
                        pass
                break

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        guild = self.bot.get_guild(payload.guild_id) if payload.guild_id else None
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return
        entries = await get_reaction_roles_for_message(payload.message_id)
        if not entries:
            return
        emoji_str = str(payload.emoji)
        for entry in entries:
            if entry.emoji == emoji_str:
                role = guild.get_role(entry.role_id)
                if role:
                    try:
                        await member.remove_roles(role, reason="Reaction-Role entfernt")
                    except discord.Forbidden:
                        pass
                break


async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionRoles(bot))
