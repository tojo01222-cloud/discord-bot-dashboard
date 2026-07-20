"""
Info- und Hilfe-Befehle. Dient als REFERENZ-Cog für alle weiteren Module:
Jeder Command wird als `hybrid_command` gebaut -> funktioniert automatisch
sowohl als /befehl (Slash) als auch als !befehl (Prefix), ohne doppelten Code.

/help überarbeitet: statt einer einzigen, bei über 100 Befehlen unübersichtlich
gewordenen Liste aus reinen Befehlsnamen (ohne Beschreibung, dicht an das
Discord-Embed-Zeichenlimit gequetscht) gibt es jetzt eine Übersicht mit
Kategorien-Anzahl PLUS ein Auswahlmenü: pro Kategorie eine übersichtliche
Liste mit Befehl UND Kurzbeschreibung.
"""
import discord
from discord.ext import commands

from bot.utils.embeds import base_embed
from bot.utils.i18n import t
from bot.utils.db_helpers import get_guild_language

# Cog-Klassenname -> (Emoji, Anzeigename, Kategorie). Cogs ohne Eintrag hier
# landen automatisch in einer "Sonstiges"-Kategorie -- diese Liste ist nur für
# schönere Beschriftung/Gruppierung, kein Muss zum Funktionieren.
COG_DISPLAY = {
    "Moderation": ("🛡️", "Moderation", "Sicherheit & Moderation"),
    "TeamManagement": ("👥", "Team", "Sicherheit & Moderation"),
    "AntiNuke": ("💣", "Anti-Nuke", "Sicherheit & Moderation"),
    "AntiSpam": ("🚫", "Anti-Spam", "Sicherheit & Moderation"),
    "AntiHack": ("🕵️", "Anti-Hack", "Sicherheit & Moderation"),
    "AntiWerbung": ("🔗", "Anti-Werbung", "Sicherheit & Moderation"),
    "Strafregister": ("📁", "Strafregister", "Sicherheit & Moderation"),
    "AutoRole": ("🤖", "Autorole", "Server-Einrichtung"),
    "Language": ("🌐", "Sprache", "Server-Einrichtung"),
    "Musik": ("🎵", "Musik", "Musik"),
    "Tickets": ("🎫", "Tickets", "Tickets & Warteraum"),
    "Warteraum": ("🙋", "Warteraum", "Tickets & Warteraum"),
    "Level": ("📈", "Level", "Community"),
    "Invites": ("📨", "Invites", "Community"),
    "Giveaway": ("🎉", "Gewinnspiele", "Community"),
    "Fun": ("🎈", "Fun", "Community"),
    "InfoHelp": ("ℹ️", "Info", "Sonstiges"),
}
CATEGORY_ORDER = [
    "Sicherheit & Moderation", "Server-Einrichtung", "Musik", "Tickets & Warteraum",
    "Community", "Sonstiges",
]
CATEGORY_EMOJI = {
    "Sicherheit & Moderation": "🛡️", "Server-Einrichtung": "⚙️", "Musik": "🎵",
    "Tickets & Warteraum": "🎫", "Community": "🌟", "Sonstiges": "📦",
}


def _collect_commands_by_category(bot: commands.Bot) -> dict[str, list[tuple[str, str]]]:
    """Baut {kategorie: [(befehl, beschreibung), ...]} aus allen geladenen Cogs."""
    by_category: dict[str, list[tuple[str, str]]] = {c: [] for c in CATEGORY_ORDER}

    for cog_name, cog in sorted(bot.cogs.items()):
        _, _, category = COG_DISPLAY.get(cog_name, ("📦", cog_name, "Sonstiges"))
        by_category.setdefault(category, [])

        for cmd in cog.get_commands():
            if isinstance(cmd, commands.Group):
                for sub in cmd.commands:
                    desc = sub.description or "—"
                    by_category[category].append((f"/{cmd.name} {sub.name}", desc))
            else:
                desc = cmd.description or "—"
                by_category[category].append((f"/{cmd.name}", desc))

    return {cat: cmds for cat, cmds in by_category.items() if cmds}


def _build_category_embed(lang: str, category: str, entries: list[tuple[str, str]]) -> discord.Embed:
    emoji = CATEGORY_EMOJI.get(category, "📦")
    embed = base_embed(f"{emoji} {category}")
    lines = [f"**`{name}`** — {desc}" for name, desc in entries]
    # Embed-Beschreibungslimit (4096 Zeichen) im Blick behalten -- bei sehr
    # befehlsreichen Kategorien lieber sauber abschneiden als einen Fehler zu riskieren.
    description = "\n".join(lines)
    if len(description) > 3900:
        description = description[:3900] + ("\n… weitere Befehle nicht angezeigt." if lang == "de"
                                              else "\n… more commands not shown.")
    embed.description = description
    embed.set_footer(text=f"{len(entries)} Befehle in dieser Kategorie" if lang == "de"
                      else f"{len(entries)} commands in this category")
    return embed


class HelpCategorySelect(discord.ui.Select):
    def __init__(self, by_category: dict[str, list[tuple[str, str]]], lang: str):
        self.by_category = by_category
        self.lang = lang
        options = [
            discord.SelectOption(label=cat, emoji=CATEGORY_EMOJI.get(cat, "📦"),
                                  description=f"{len(cmds)} Befehle" if lang == "de" else f"{len(cmds)} commands")
            for cat, cmds in by_category.items()
        ]
        placeholder = "Kategorie wählen..." if lang == "de" else "Choose a category..."
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        embed = _build_category_embed(self.lang, category, self.by_category[category])
        await interaction.response.edit_message(embed=embed)


class HelpView(discord.ui.View):
    def __init__(self, by_category: dict[str, list[tuple[str, str]]], lang: str):
        super().__init__(timeout=120)
        self.add_item(HelpCategorySelect(by_category, lang))

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True


class InfoHelp(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="help", description="Zeigt alle verfügbaren Befehle, gruppiert nach Kategorie.")
    async def help_command(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id) if ctx.guild else "de"
        by_category = _collect_commands_by_category(self.bot)
        total_commands = sum(len(cmds) for cmds in by_category.values())

        embed = base_embed(t("help.title", lang))
        overview_lines = []
        for cat in CATEGORY_ORDER:
            if cat not in by_category:
                continue
            emoji = CATEGORY_EMOJI.get(cat, "📦")
            count = len(by_category[cat])
            plural = "Befehle" if lang == "de" else "commands"
            overview_lines.append(f"{emoji} **{cat}** — {count} {plural}")
        embed.description = (
            ("Wähle unten eine Kategorie aus, um die Befehle mit Beschreibung zu sehen.\n\n"
             if lang == "de" else
             "Pick a category below to see its commands with descriptions.\n\n")
            + "\n".join(overview_lines)
        )
        embed.set_footer(text=f"{total_commands} Befehle insgesamt" if lang == "de"
                          else f"{total_commands} commands total")

        view = HelpView(by_category, lang)
        await ctx.send(embed=embed, view=view)

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
