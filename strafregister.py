"""
Wortfilter -- löscht Nachrichten automatisch, die verbotene Wörter enthalten.

- /wortfilter add <wort>       -- fügt ein verbotenes Wort hinzu (SERVER_ADMIN)
- /wortfilter liste             -- zeigt alle verbotenen Wörter
- /wortfilter entfernen <id>     -- entfernt ein Wort (SERVER_ADMIN)

Wie bei Anti-Spam/Anti-Hack: die Wortliste wird gecacht (TTL), damit nicht
bei jeder einzelnen Nachricht eine Datenbankabfrage nötig ist.
"""
import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, error_embed, base_embed
from bot.utils.db_helpers import get_guild_language, add_banned_word, get_banned_words, remove_banned_word

_word_cache: dict[int, tuple] = {}  # guild_id -> (timestamp, set(wörter))
_CACHE_TTL = 60


async def _get_cached_words(guild_id: int) -> set[str]:
    now = dt.datetime.utcnow().timestamp()
    cached = _word_cache.get(guild_id)
    if cached and now - cached[0] < _CACHE_TTL:
        return cached[1]
    entries = await get_banned_words(guild_id)
    words = {e.word for e in entries}
    _word_cache[guild_id] = (now, words)
    return words


class Wortfilter(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_group(name="wortfilter", description="Wortfilter verwalten.")
    @commands.guild_only()
    async def wortfilter(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @wortfilter.command(name="add", description="Fügt ein verbotenes Wort hinzu.")
    @app_commands.describe(wort="Das zu blockierende Wort")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def wortfilter_add(self, ctx: commands.Context, wort: str):
        await add_banned_word(ctx.guild.id, wort)
        _word_cache.pop(ctx.guild.id, None)
        await ctx.send(embed=success_embed(f"Wort zur Wortfilter-Liste hinzugefügt: {wort}"))

    @wortfilter.command(name="liste", description="Zeigt alle verbotenen Wörter.")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def wortfilter_liste(self, ctx: commands.Context):
        entries = await get_banned_words(ctx.guild.id)
        if not entries:
            await ctx.send(embed=error_embed("Keine Wörter eingerichtet."), ephemeral=True)
            return
        lines = [f"#{e.id} — {e.word}" for e in entries]
        await ctx.send(embed=base_embed("🚫 Wortfilter", "\n".join(lines)), ephemeral=True)

    @wortfilter.command(name="entfernen", description="Entfernt ein Wort aus der Liste.")
    @app_commands.describe(entry_id="Die ID aus /wortfilter liste")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def wortfilter_entfernen(self, ctx: commands.Context, entry_id: int):
        ok = await remove_banned_word(entry_id)
        _word_cache.pop(ctx.guild.id, None)
        await ctx.send(embed=success_embed("Entfernt.") if ok else error_embed("ID nicht gefunden."))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        words = await _get_cached_words(message.guild.id)
        if not words:
            return
        content_lower = message.content.lower()
        if any(w in content_lower for w in words):
            try:
                await message.delete()
            except discord.Forbidden:
                return
            lang = await get_guild_language(message.guild.id)
            try:
                await message.channel.send(
                    f"{message.author.mention} " + (
                        "deine Nachricht enthielt ein nicht erlaubtes Wort." if lang == "de"
                        else "your message contained a disallowed word."
                    ), delete_after=6,
                )
            except discord.Forbidden:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Wortfilter(bot))
