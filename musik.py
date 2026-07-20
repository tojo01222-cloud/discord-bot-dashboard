"""
Werbungs- und Partner-System.

- /werbung kanal <kanal>                     -- legt den Werbe-Kanal fest (SERVER_ADMIN)
- /werbung erstellen <text>                   -- postet eine formatierte Werbe-Anzeige dort
- /partner add <name> <einladungslink>         -- fügt einen Partner-Server hinzu (SERVER_ADMIN)
- /partner list                                 -- zeigt alle Partner
- /partner remove <id>                          -- entfernt einen Partner (SERVER_ADMIN)

Bewusst KEIN automatisches Cross-Posting in den Partner-Server selbst -- das
würde voraussetzen, dass der Bot auch dort ist und Schreibrechte hat, was
nicht garantiert werden kann. Stattdessen: eine gepflegte Partnerliste mit
Einladungslinks.
"""
import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, error_embed, base_embed
from bot.utils.db_helpers import (
    get_guild_language,
    get_ad_channel,
    set_ad_channel,
    add_partner,
    get_partners,
    remove_partner,
)


class Werbung(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_group(name="werbung", description="Werbungs-System verwalten.")
    @commands.guild_only()
    async def werbung(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @werbung.command(name="kanal", description="Legt den Kanal für Werbe-Anzeigen fest.")
    @app_commands.describe(kanal="Der Zielkanal")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def werbung_kanal(self, ctx: commands.Context, kanal: discord.TextChannel):
        lang = await get_guild_language(ctx.guild.id)
        await set_ad_channel(ctx.guild.id, kanal.id)
        await ctx.send(embed=success_embed(
            f"Werbe-Kanal auf {kanal.mention} gesetzt." if lang == "de"
            else f"Ad channel set to {kanal.mention}."))

    @werbung.command(name="erstellen", description="Postet eine Werbe-Anzeige im eingerichteten Kanal.")
    @app_commands.describe(text="Der Werbetext")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def werbung_erstellen(self, ctx: commands.Context, *, text: str):
        lang = await get_guild_language(ctx.guild.id)
        channel_id = await get_ad_channel(ctx.guild.id)
        if not channel_id:
            await ctx.send(embed=error_embed(
                "Noch kein Werbe-Kanal eingerichtet -- nutze zuerst `/werbung kanal`." if lang == "de"
                else "No ad channel configured yet -- use `/werbung kanal` first."))
            return

        channel = ctx.guild.get_channel(channel_id)
        if not channel:
            await ctx.send(embed=error_embed(
                "Der eingerichtete Werbe-Kanal existiert nicht mehr." if lang == "de"
                else "The configured ad channel no longer exists."))
            return

        embed = base_embed("📢 " + ("Werbung" if lang == "de" else "Advertisement"), text)
        embed.set_footer(text=f"{ctx.guild.name}")
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            await ctx.send(embed=error_embed(
                f"Ich kann in {channel.mention} nicht schreiben." if lang == "de"
                else f"I can't send messages in {channel.mention}."))
            return

        await ctx.send(embed=success_embed(
            f"Anzeige in {channel.mention} gepostet." if lang == "de"
            else f"Ad posted in {channel.mention}."), ephemeral=True)

    @commands.hybrid_group(name="partner", description="Partner-Server verwalten.")
    @commands.guild_only()
    async def partner(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @partner.command(name="add", description="Fügt einen Partner-Server hinzu.")
    @app_commands.describe(name="Name des Partner-Servers", einladungslink="Discord-Einladungslink")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def partner_add(self, ctx: commands.Context, name: str, einladungslink: str):
        lang = await get_guild_language(ctx.guild.id)
        await add_partner(ctx.guild.id, name, einladungslink, ctx.author.id)
        await ctx.send(embed=success_embed(
            f"Partner **{name}** hinzugefügt." if lang == "de" else f"Partner **{name}** added."))

    @partner.command(name="list", description="Zeigt alle Partner-Server.")
    async def partner_list(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        partners = await get_partners(ctx.guild.id)
        if not partners:
            await ctx.send(embed=error_embed(
                "Noch keine Partner eingetragen." if lang == "de" else "No partners yet."))
            return

        embed = base_embed("🤝 " + ("Partner-Server" if lang == "de" else "Partner Servers"))
        embed.description = "\n".join(f"#{p.id} — **{p.name}** — {p.invite_link}" for p in partners[:25])
        await ctx.send(embed=embed)

    @partner.command(name="remove", description="Entfernt einen Partner-Server.")
    @app_commands.describe(partner_id="Die ID aus /partner list")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def partner_remove(self, ctx: commands.Context, partner_id: int):
        lang = await get_guild_language(ctx.guild.id)
        ok = await remove_partner(partner_id)
        if ok:
            await ctx.send(embed=success_embed("Partner entfernt." if lang == "de" else "Partner removed."))
        else:
            await ctx.send(embed=error_embed("ID nicht gefunden." if lang == "de" else "ID not found."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Werbung(bot))
