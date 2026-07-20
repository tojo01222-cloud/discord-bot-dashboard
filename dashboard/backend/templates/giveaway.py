"""
Sprach-System.

- /language <de|en>              -- stellt die Sprache des Bots für diesen Server ein (SERVER_ADMIN)
- /language_aktualisieren <de|en> -- setzt die Sprache UND synchronisiert die Slash-Commands sofort
                                      neu für DIESEN Server, statt auf die normale (bis zu einer
                                      Stunde dauernde) globale Synchronisierung zu warten (SERVER_ADMIN)

Standard-Sprache eines neuen Servers ist Englisch (siehe Config.DEFAULT_LANGUAGE),
danach über /language pro Server umstellbar. Betrifft alle Bot-generierten
Nachrichten (Embeds, Fehlermeldungen, usw.), die über t()/lang-Verzweigungen
laufen -- also praktisch den gesamten Bot.

WICHTIGER HINWEIS zu Discords eigener Lokalisierung: Die Namen/Beschreibungen
der Slash-Commands selbst (wie sie im "/"-Menü erscheinen) werden von Discord
IMMER nach der individuellen Sprach-Einstellung JEDES EINZELNEN Users
angezeigt, nicht nach einer Server-weiten Einstellung -- das ist eine
Discord-Plattform-Grenze, die kein Bot umgehen kann. /language stellt daher
gezielt die Sprache der Bot-ANTWORTEN (Embeds, Nachrichten) ein, was der
Server tatsächlich zentral steuern kann.
"""
import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, error_embed
from bot.utils.i18n import t
from bot.utils.db_helpers import get_guild_language, set_guild_language

LANGUAGE_CHOICES = [
    app_commands.Choice(name="Deutsch", value="de"),
    app_commands.Choice(name="English", value="en"),
    app_commands.Choice(name="Español", value="es"),
]
LANGUAGE_LABELS = {"de": "Deutsch", "en": "English", "es": "Español"}
VALID_LANGUAGES = ("de", "en", "es")


class Language(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="language", description="Stellt die Sprache des Bots für diesen Server ein (de/en/es).")
    @app_commands.describe(sprache="de für Deutsch, en für Englisch, es für Spanisch")
    @app_commands.choices(sprache=LANGUAGE_CHOICES)
    @commands.guild_only()
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def language(self, ctx: commands.Context, sprache: str):
        if sprache not in VALID_LANGUAGES:
            current_lang = await get_guild_language(ctx.guild.id)
            await ctx.send(embed=error_embed("Ungültige Sprache -- nutze 'de', 'en' oder 'es'." if current_lang == "de"
                                              else "Invalid language -- use 'de', 'en', or 'es'."))
            return

        await set_guild_language(ctx.guild.id, sprache)
        await ctx.send(embed=success_embed(t("language.set", sprache, language=LANGUAGE_LABELS[sprache])))

    @commands.hybrid_command(
        name="language_aktualisieren",
        description="Setzt die Sprache und synchronisiert die Slash-Commands sofort neu für diesen Server.",
    )
    @app_commands.describe(sprache="de für Deutsch, en für Englisch, es für Spanisch")
    @app_commands.choices(sprache=LANGUAGE_CHOICES)
    @commands.guild_only()
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def language_aktualisieren(self, ctx: commands.Context, sprache: str):
        if sprache not in VALID_LANGUAGES:
            current_lang = await get_guild_language(ctx.guild.id)
            await ctx.send(embed=error_embed("Ungültige Sprache -- nutze 'de', 'en' oder 'es'." if current_lang == "de"
                                              else "Invalid language -- use 'de', 'en', or 'es'."))
            return

        await ctx.defer()
        await set_guild_language(ctx.guild.id, sprache)

        try:
            synced = await self.bot.tree.sync(guild=ctx.guild)
            sync_note = (f"\n{len(synced)} Befehle für diesen Server sofort synchronisiert." if sprache == "de"
                         else f"\n{len(synced)} commands synced instantly for this server.")
        except discord.HTTPException:
            sync_note = ("\n⚠️ Sofort-Synchronisierung fehlgeschlagen -- die normale globale "
                         "Synchronisierung greift trotzdem innerhalb der nächsten Stunde." if sprache == "de" else
                         "\n⚠️ Instant sync failed -- the regular global sync will still apply "
                         "within the next hour.")

        embed = success_embed(t("language.refreshed", sprache))
        embed.description = (embed.description or "") + sync_note
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Language(bot))
