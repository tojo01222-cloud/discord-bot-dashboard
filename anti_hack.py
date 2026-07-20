"""
Vorschlagssystem.

- /vorschlag kanal <kanal>          -- legt den Vorschlags-Kanal fest (SERVER_ADMIN)
- /vorschlag erstellen <text>        -- reicht einen Vorschlag ein, postet ihn mit
                                         👍/👎-Reaktionen zur Abstimmung
- /vorschlag annehmen <id>            -- markiert einen Vorschlag als angenommen (TEAM)
- /vorschlag ablehnen <id>            -- markiert einen Vorschlag als abgelehnt (TEAM)
- /vorschlag liste [status]           -- zeigt Vorschläge, optional gefiltert
"""
import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, error_embed, base_embed
from bot.utils.db_helpers import (
    get_guild_language,
    get_suggestion_channel,
    set_suggestion_channel,
    create_suggestion,
    set_suggestion_message_id,
    update_suggestion_status,
    get_suggestions,
)

STATUS_CHOICES = [
    app_commands.Choice(name="Offen", value="pending"),
    app_commands.Choice(name="Angenommen", value="accepted"),
    app_commands.Choice(name="Abgelehnt", value="rejected"),
]
STATUS_LABELS = {"pending": "🟡 Offen", "accepted": "✅ Angenommen", "rejected": "❌ Abgelehnt"}


class Suggestions(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_group(name="vorschlag", description="Vorschlagssystem verwalten.")
    @commands.guild_only()
    async def vorschlag(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @vorschlag.command(name="kanal", description="Legt den Kanal für Vorschläge fest.")
    @app_commands.describe(kanal="Der Zielkanal")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def vorschlag_kanal(self, ctx: commands.Context, kanal: discord.TextChannel):
        lang = await get_guild_language(ctx.guild.id)
        await set_suggestion_channel(ctx.guild.id, kanal.id)
        await ctx.send(embed=success_embed(
            f"Vorschlags-Kanal auf {kanal.mention} gesetzt." if lang == "de"
            else f"Suggestion channel set to {kanal.mention}."))

    @vorschlag.command(name="erstellen", description="Reicht einen Vorschlag ein.")
    @app_commands.describe(text="Dein Vorschlag")
    @commands.guild_only()
    async def vorschlag_erstellen(self, ctx: commands.Context, *, text: str):
        lang = await get_guild_language(ctx.guild.id)
        channel_id = await get_suggestion_channel(ctx.guild.id)
        if not channel_id:
            await ctx.send(embed=error_embed(
                "Noch kein Vorschlags-Kanal eingerichtet." if lang == "de"
                else "No suggestion channel configured yet."), ephemeral=True)
            return

        channel = ctx.guild.get_channel(channel_id)
        if not channel:
            await ctx.send(embed=error_embed(
                "Der eingerichtete Kanal existiert nicht mehr." if lang == "de"
                else "The configured channel no longer exists."), ephemeral=True)
            return

        suggestion = await create_suggestion(ctx.guild.id, ctx.author.id, text)

        embed = base_embed(f"💡 Vorschlag #{suggestion.id}" if lang == "de" else f"💡 Suggestion #{suggestion.id}", text)
        embed.set_footer(text=f"Von {ctx.author.display_name}")
        try:
            message = await channel.send(embed=embed)
            await message.add_reaction("👍")
            await message.add_reaction("👎")
        except discord.Forbidden:
            await ctx.send(embed=error_embed(
                f"Ich kann in {channel.mention} nicht schreiben." if lang == "de"
                else f"I can't send messages in {channel.mention}."), ephemeral=True)
            return

        await set_suggestion_message_id(suggestion.id, message.id)
        await ctx.send(embed=success_embed(
            f"Vorschlag in {channel.mention} gepostet." if lang == "de"
            else f"Suggestion posted in {channel.mention}."), ephemeral=True)

    @vorschlag.command(name="annehmen", description="Markiert einen Vorschlag als angenommen.")
    @app_commands.describe(vorschlag_id="Die ID des Vorschlags")
    @commands.guild_only()
    @require_level(PermissionLevel.TEAM)
    async def vorschlag_annehmen(self, ctx: commands.Context, vorschlag_id: int):
        await self._update_status(ctx, vorschlag_id, "accepted")

    @vorschlag.command(name="ablehnen", description="Markiert einen Vorschlag als abgelehnt.")
    @app_commands.describe(vorschlag_id="Die ID des Vorschlags")
    @commands.guild_only()
    @require_level(PermissionLevel.TEAM)
    async def vorschlag_ablehnen(self, ctx: commands.Context, vorschlag_id: int):
        await self._update_status(ctx, vorschlag_id, "rejected")

    async def _update_status(self, ctx: commands.Context, suggestion_id: int, status: str) -> None:
        lang = await get_guild_language(ctx.guild.id)
        suggestion = await update_suggestion_status(suggestion_id, status)
        if suggestion is None:
            await ctx.send(embed=error_embed("Vorschlag nicht gefunden." if lang == "de" else "Suggestion not found."))
            return

        await ctx.send(embed=success_embed(
            f"Vorschlag #{suggestion_id} als {STATUS_LABELS[status]} markiert." if lang == "de"
            else f"Suggestion #{suggestion_id} marked as {STATUS_LABELS[status]}."))

        if suggestion.message_id:
            channel_id = await get_suggestion_channel(ctx.guild.id)
            channel = ctx.guild.get_channel(channel_id) if channel_id else None
            if channel:
                try:
                    message = await channel.fetch_message(suggestion.message_id)
                    if message.embeds:
                        embed = message.embeds[0]
                        embed.add_field(name="Status", value=STATUS_LABELS[status], inline=False)
                        await message.edit(embed=embed)
                except (discord.NotFound, discord.Forbidden):
                    pass

    @vorschlag.command(name="liste", description="Zeigt eingereichte Vorschläge.")
    @app_commands.describe(status="Optional: nur einen bestimmten Status anzeigen")
    @app_commands.choices(status=STATUS_CHOICES)
    async def vorschlag_liste(self, ctx: commands.Context, status: str = None):
        lang = await get_guild_language(ctx.guild.id)
        suggestions = await get_suggestions(ctx.guild.id, status)
        if not suggestions:
            await ctx.send(embed=error_embed("Keine Vorschläge gefunden." if lang == "de" else "No suggestions found."))
            return

        embed = base_embed("💡 Vorschläge" if lang == "de" else "💡 Suggestions")
        lines = [f"#{s.id} — {STATUS_LABELS[s.status]} — {s.content[:60]}" for s in suggestions[:20]]
        embed.description = "\n".join(lines)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Suggestions(bot))
