"""
Sticky Messages -- eine Nachricht, die immer am unteren Ende eines Kanals
bleibt. Bei jeder neuen Nachricht im Kanal wird die alte Sticky-Nachricht
gelöscht und am Ende neu gepostet.

- /sticky_setzen <text>    -- richtet eine Sticky-Nachricht für den aktuellen Kanal ein (SERVER_ADMIN)
- /sticky_entfernen         -- entfernt sie wieder (SERVER_ADMIN)
"""
import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, error_embed
from bot.utils.db_helpers import (
    get_guild_language,
    set_sticky_message,
    get_sticky_message,
    update_sticky_last_message_id,
    remove_sticky_message,
)

# channel_id -> Sticky-Objekt, TTL-gecacht. WICHTIG: ohne diesen Cache würde
# on_message() bei JEDER Nachricht in JEDEM Kanal eine DB-Abfrage auslösen --
# dieselbe Lektion wie beim früheren Anti-Spam-Performance-Bug.
_sticky_cache: dict[int, tuple] = {}
_STICKY_CACHE_TTL = 30  # Sekunden


class Sticky(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="sticky_setzen", description="Richtet eine Sticky-Nachricht für diesen Kanal ein.")
    @app_commands.describe(text="Der Text, der immer unten im Kanal bleiben soll")
    @commands.guild_only()
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def sticky_setzen(self, ctx: commands.Context, *, text: str):
        lang = await get_guild_language(ctx.guild.id)
        await set_sticky_message(ctx.channel.id, ctx.guild.id, text)
        message = await ctx.send(text)
        await update_sticky_last_message_id(ctx.channel.id, message.id)
        _sticky_cache.pop(ctx.channel.id, None)  # nächster Treffer holt frisch aus der DB
        await ctx.send(embed=success_embed(
            "📌 Sticky-Nachricht eingerichtet." if lang == "de" else "📌 Sticky message set up."), ephemeral=True)

    @commands.hybrid_command(name="sticky_entfernen", description="Entfernt die Sticky-Nachricht dieses Kanals.")
    @commands.guild_only()
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def sticky_entfernen(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        ok = await remove_sticky_message(ctx.channel.id)
        _sticky_cache.pop(ctx.channel.id, None)
        await ctx.send(embed=success_embed("Entfernt." if lang == "de" else "Removed.") if ok
                        else error_embed("Kein Sticky in diesem Kanal." if lang == "de" else "No sticky in this channel."))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        import datetime as dt
        now = dt.datetime.utcnow().timestamp()
        cached = _sticky_cache.get(message.channel.id)
        if cached and now - cached[0] < _STICKY_CACHE_TTL:
            sticky = cached[1]
        else:
            sticky = await get_sticky_message(message.channel.id)
            _sticky_cache[message.channel.id] = (now, sticky)

        if sticky is None:
            return
        if sticky.last_message_id:
            try:
                old = await message.channel.fetch_message(sticky.last_message_id)
                await old.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        try:
            new_message = await message.channel.send(sticky.content)
            await update_sticky_last_message_id(message.channel.id, new_message.id)
            # Cache mit der neuen last_message_id aktualisieren, damit der
            # nächste Treffer innerhalb der TTL nicht die alte ID nochmal löscht.
            sticky.last_message_id = new_message.id
            _sticky_cache[message.channel.id] = (now, sticky)
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Sticky(bot))
