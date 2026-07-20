"""
Info- und Hilfe-Befehle. Dient als REFERENZ-Cog für alle weiteren Module:
Jeder Command wird als `hybrid_command` gebaut -> funktioniert automatisch
sowohl als /befehl (Slash) als auch als !befehl (Prefix), ohne doppelten Code.
"""
import discord
from discord.ext import commands

from bot.utils.embeds import base_embed
from bot.utils.i18n import t
from bot.utils.db_helpers import get_guild_language

# Anzeigename + Emoji pro Cog-Klasse, fürs /help-Kommando. Ein neuer Cog ohne
# Eintrag hier taucht trotzdem auf (mit Klassennamen als Fallback) -- diese
# Liste ist nur für schönere Beschriftung, kein Muss zum Funktionieren.
COG_DISPLAY = {
    "Moderation": ("🛡️", "Moderation"),
    "TeamManagement": ("👥", "Team"),
    "AntiNuke": ("💣", "Anti-Nuke"),
    "AntiSpam": ("🚫", "Anti-Spam"),
    "Musik": ("🎵", "Musik"),
    "Tickets": ("🎫", "Tickets"),
    "Warteraum": ("🙋", "Warteraum"),
    "Level": ("📈", "Level"),
    "Invites": ("📨", "Invites"),
    "Giveaway": ("🎉", "Gewinnspiele"),
    "Fun": ("🎈", "Fun"),
    "InfoHelp": ("ℹ️", "Info"),
}


class InfoHelp(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="help", description="Zeigt alle verfügbaren Befehle mit Beschreibung.")
    async def help_command(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id) if ctx.guild else "de"

        embed = base_embed(t("help.title", lang))
        total_commands = 0
        total_chars = len(embed.title or "")

        for cog_name, cog in sorted(self.bot.cogs.items()):
            lines = []
            for cmd in cog.get_commands():
                if isinstance(cmd, commands.Group):
                    for sub in cmd.commands:
                        lines.append(f"`/{cmd.name} {sub.name}`")
                        total_commands += 1
                else:
                    lines.append(f"`/{cmd.name}`")
                    total_commands += 1

            if not lines:
                continue

            emoji, display_name = COG_DISPLAY.get(cog_name, ("📦", cog_name))
            value = " ".join(lines)
            if len(value) > 1000:  # Discord-Embed-Feldlimit (1024) mit Puffer
                value = value[:1000] + " ..."

            # Discord begrenzt nicht nur jedes Feld einzeln, sondern auch das
            # GESAMTE Embed auf 6000 Zeichen -- bei über 70 Befehlen inzwischen
            # real relevant. Sicherheitsmarge bei 5500, danach nur noch ein
            # Sammel-Hinweis statt eines weiteren vollen Feldes.
            field_name = f"{emoji} {display_name}"
            if total_chars + len(field_name) + len(value) > 5500:
                embed.add_field(
                    name="…" if lang == "de" else "…",
                    value=("Es gibt noch mehr Befehle, als in eine Nachricht passen — frag ein "
                           "Team-Mitglied oder schau in der Dokumentation nach der vollständigen Liste."
                           if lang == "de" else
                           "There are more commands than fit in one message — ask a team member "
                           "or check the documentation for the full list."),
                    inline=False,
                )
                break

            embed.add_field(name=field_name, value=value, inline=False)
            total_chars += len(field_name) + len(value)

        embed.set_footer(text=f"{total_commands} Befehle insgesamt" if lang == "de"
                          else f"{total_commands} commands total")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="serverinfo", description="Zeigt Informationen über diesen Server.")
    @commands.guild_only()
    async def serverinfo(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        guild = ctx.guild

        embed = base_embed(t("serverinfo.title", lang))
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Name", value=guild.name, inline=True)
        embed.add_field(name="Owner", value=str(guild.owner), inline=True)
        embed.add_field(name="Mitglieder" if lang == "de" else "Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Erstellt am" if lang == "de" else "Created at",
                         value=discord.utils.format_dt(guild.created_at, style="D"), inline=True)
        embed.add_field(name="Rollen" if lang == "de" else "Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Kanäle" if lang == "de" else "Channels", value=str(len(guild.channels)), inline=True)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(InfoHelp(bot))
