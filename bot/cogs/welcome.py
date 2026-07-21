"""
Willkommen/Abschied-System.

- /willkommen kanal <kanal>     -- legt den Kanal fest UND aktiviert die Willkommensnachricht (SERVER_ADMIN)
- /willkommen nachricht <text>  -- setzt den Nachrichtentext, Platzhalter: {user} {name} {server} {membercount} (SERVER_ADMIN)
- /willkommen test              -- sendet eine Vorschau in den aktuellen Kanal
- /willkommen aus               -- deaktiviert die Willkommensnachricht (SERVER_ADMIN)

- /abschied kanal|nachricht|test|aus -- identisch, für die Abschiedsnachricht beim Verlassen

Bewusst schlank gehalten: kein separates Enable/Disable-Feld zusätzlich zum
Kanal-Befehl -- /willkommen kanal setzt UND aktiviert in einem Schritt,
/willkommen aus deaktiviert wieder, ohne den gespeicherten Kanal/Text zu löschen
(einfaches Wiederaktivieren möglich, ohne alles neu einzurichten).
"""

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, error_embed
from bot.utils.db_helpers import get_guild_language, get_welcome_config, set_welcome_settings

PLACEHOLDER_HELP_DE = "Platzhalter: {user} (Erwähnung), {name} (Name), {server} (Servername), {membercount} (Mitgliederzahl)"
PLACEHOLDER_HELP_EN = "Placeholders: {user} (mention), {name} (name), {server} (server name), {membercount} (member count)"


def _format_message(template: str, member: discord.Member) -> str:
    guild = member.guild
    try:
        return template.format(
            user=member.mention,
            name=member.display_name,
            server=guild.name,
            membercount=guild.member_count,
        )
    except (KeyError, IndexError):
        # Ungültiger Platzhalter im gespeicherten Text -- lieber den rohen Text
        # zeigen als mit einem Fehler abzustürzen.
        return template


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- Listener ----------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        cfg = await get_welcome_config(member.guild.id)
        if not cfg.welcome_enabled or not cfg.welcome_channel_id:
            return
        channel = member.guild.get_channel(cfg.welcome_channel_id)
        if not channel:
            return
        embed = discord.Embed(
            description=_format_message(cfg.welcome_message, member),
            color=discord.Color.green(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        cfg = await get_welcome_config(member.guild.id)
        if not cfg.goodbye_enabled or not cfg.goodbye_channel_id:
            return
        channel = member.guild.get_channel(cfg.goodbye_channel_id)
        if not channel:
            return
        embed = discord.Embed(
            description=_format_message(cfg.goodbye_message, member),
            color=discord.Color.dark_grey(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

    # ---------- /willkommen ----------

    @commands.hybrid_group(name="willkommen", description="Willkommensnachricht verwalten.")
    @commands.guild_only()
    async def willkommen(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @willkommen.command(name="kanal", description="Legt den Kanal fest und aktiviert die Willkommensnachricht.")
    @app_commands.describe(kanal="Zielkanal für neue Willkommensnachrichten")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def willkommen_kanal(self, ctx: commands.Context, kanal: discord.TextChannel):
        lang = await get_guild_language(ctx.guild.id)
        await set_welcome_settings(ctx.guild.id, welcome_enabled=True, welcome_channel_id=kanal.id)
        await ctx.send(embed=success_embed(
            "Willkommensnachricht aktiviert" if lang == "de" else "Welcome message enabled",
            f"Kanal: {kanal.mention}" if lang == "de" else f"Channel: {kanal.mention}",
        ))

    @willkommen.command(name="nachricht", description="Setzt den Text der Willkommensnachricht.")
    @app_commands.describe(text=PLACEHOLDER_HELP_DE)
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def willkommen_nachricht(self, ctx: commands.Context, *, text: str):
        lang = await get_guild_language(ctx.guild.id)
        await set_welcome_settings(ctx.guild.id, welcome_message=text)
        await ctx.send(embed=success_embed(
            "Nachricht gespeichert" if lang == "de" else "Message saved",
            (PLACEHOLDER_HELP_DE if lang == "de" else PLACEHOLDER_HELP_EN),
        ))

    @willkommen.command(name="test", description="Zeigt eine Vorschau der Willkommensnachricht in diesem Kanal.")
    async def willkommen_test(self, ctx: commands.Context):
        cfg = await get_welcome_config(ctx.guild.id)
        embed = discord.Embed(description=_format_message(cfg.welcome_message, ctx.author), color=discord.Color.green())
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @willkommen.command(name="aus", description="Deaktiviert die Willkommensnachricht.")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def willkommen_aus(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        await set_welcome_settings(ctx.guild.id, welcome_enabled=False)
        await ctx.send(embed=success_embed("Deaktiviert" if lang == "de" else "Disabled"))

    # ---------- /abschied ----------

    @commands.hybrid_group(name="abschied", description="Abschiedsnachricht verwalten.")
    @commands.guild_only()
    async def abschied(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @abschied.command(name="kanal", description="Legt den Kanal fest und aktiviert die Abschiedsnachricht.")
    @app_commands.describe(kanal="Zielkanal für Abschiedsnachrichten")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def abschied_kanal(self, ctx: commands.Context, kanal: discord.TextChannel):
        lang = await get_guild_language(ctx.guild.id)
        await set_welcome_settings(ctx.guild.id, goodbye_enabled=True, goodbye_channel_id=kanal.id)
        await ctx.send(embed=success_embed(
            "Abschiedsnachricht aktiviert" if lang == "de" else "Goodbye message enabled",
            f"Kanal: {kanal.mention}" if lang == "de" else f"Channel: {kanal.mention}",
        ))

    @abschied.command(name="nachricht", description="Setzt den Text der Abschiedsnachricht.")
    @app_commands.describe(text=PLACEHOLDER_HELP_DE)
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def abschied_nachricht(self, ctx: commands.Context, *, text: str):
        lang = await get_guild_language(ctx.guild.id)
        await set_welcome_settings(ctx.guild.id, goodbye_message=text)
        await ctx.send(embed=success_embed(
            "Nachricht gespeichert" if lang == "de" else "Message saved",
            (PLACEHOLDER_HELP_DE if lang == "de" else PLACEHOLDER_HELP_EN),
        ))

    @abschied.command(name="test", description="Zeigt eine Vorschau der Abschiedsnachricht in diesem Kanal.")
    async def abschied_test(self, ctx: commands.Context):
        cfg = await get_welcome_config(ctx.guild.id)
        embed = discord.Embed(description=_format_message(cfg.goodbye_message, ctx.author), color=discord.Color.dark_grey())
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @abschied.command(name="aus", description="Deaktiviert die Abschiedsnachricht.")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def abschied_aus(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        await set_welcome_settings(ctx.guild.id, goodbye_enabled=False)
        await ctx.send(embed=success_embed("Deaktiviert" if lang == "de" else "Disabled"))


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
