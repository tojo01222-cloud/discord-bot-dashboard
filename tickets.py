"""
Umfragen mit mehreren Optionen und dauerhafter Auswertung (anders als das
einfache 👍/👎 im Vorschlagssystem).

- /poll_erstellen <frage> <optionen>   -- Optionen durch Komma getrennt (max. 10)
- /poll_ergebnisse <id>                 -- zeigt die aktuelle Auswertung
- /poll_schliessen <id>                  -- schließt die Umfrage (TEAM)
"""
import json

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, error_embed, base_embed
from bot.database.db import get_session
from bot.database.models import Poll as PollModel
from bot.utils.db_helpers import (
    get_guild_language,
    create_poll,
    set_poll_message_id,
    get_poll,
    cast_poll_vote,
    get_poll_results,
    close_poll,
)

NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def _build_results_embed(question: str, options: list[str], counts: dict[int, int], closed: bool) -> discord.Embed:
    total = sum(counts.values())
    lines = []
    for i, opt in enumerate(options):
        votes = counts.get(i, 0)
        percent = round((votes / total) * 100) if total else 0
        bar = "█" * (percent // 10) + "░" * (10 - percent // 10)
        lines.append(f"{NUMBER_EMOJIS[i]} {opt}\n`{bar}` {votes} ({percent}%)")
    embed = base_embed(("🔒 " if closed else "📊 ") + question)
    embed.description = "\n\n".join(lines) + f"\n\n**{total}** Stimmen insgesamt"
    return embed


class Polls(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="poll_erstellen", description="Erstellt eine Umfrage mit mehreren Optionen.")
    @app_commands.describe(frage="Die Frage", optionen="Antwortmöglichkeiten, durch Komma getrennt (max. 10)")
    @commands.guild_only()
    async def poll_erstellen(self, ctx: commands.Context, frage: str, *, optionen: str):
        lang = await get_guild_language(ctx.guild.id)
        options = [o.strip() for o in optionen.split(",") if o.strip()][:10]
        if len(options) < 2:
            await ctx.send(embed=error_embed(
                "Gib mindestens 2 Optionen an, durch Komma getrennt." if lang == "de"
                else "Provide at least 2 options, comma-separated."), ephemeral=True)
            return

        poll = await create_poll(ctx.guild.id, ctx.channel.id, frage, options, ctx.author.id)
        embed = _build_results_embed(frage, options, {}, closed=False)
        embed.set_footer(text=f"Umfrage #{poll.id} — reagiere zum Abstimmen")

        message = await ctx.send(embed=embed)
        await set_poll_message_id(poll.id, message.id)
        for i in range(len(options)):
            await message.add_reaction(NUMBER_EMOJIS[i])

    @commands.hybrid_command(name="poll_ergebnisse", description="Zeigt die aktuelle Auswertung einer Umfrage.")
    @app_commands.describe(poll_id="Die Umfrage-ID")
    @commands.guild_only()
    async def poll_ergebnisse(self, ctx: commands.Context, poll_id: int):
        lang = await get_guild_language(ctx.guild.id)
        poll = await get_poll(poll_id)
        if poll is None or poll.guild_id != ctx.guild.id:
            await ctx.send(embed=error_embed("Umfrage nicht gefunden." if lang == "de" else "Poll not found."))
            return
        options = json.loads(poll.options_json)
        counts = await get_poll_results(poll_id)
        await ctx.send(embed=_build_results_embed(poll.question, options, counts, poll.closed))

    @commands.hybrid_command(name="poll_schliessen", description="Schließt eine Umfrage.")
    @app_commands.describe(poll_id="Die Umfrage-ID")
    @commands.guild_only()
    @require_level(PermissionLevel.TEAM)
    async def poll_schliessen(self, ctx: commands.Context, poll_id: int):
        lang = await get_guild_language(ctx.guild.id)
        poll = await get_poll(poll_id)
        if poll is None or poll.guild_id != ctx.guild.id:
            await ctx.send(embed=error_embed("Umfrage nicht gefunden." if lang == "de" else "Poll not found."))
            return
        await close_poll(poll_id)
        await ctx.send(embed=success_embed("Umfrage geschlossen." if lang == "de" else "Poll closed."))

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.member is None or payload.member.bot:
            return
        emoji_str = str(payload.emoji)
        if emoji_str not in NUMBER_EMOJIS:
            return

        async with get_session() as session:
            stmt = select(PollModel).where(PollModel.message_id == payload.message_id)
            poll = (await session.execute(stmt)).scalar_one_or_none()
        if poll is None or poll.closed:
            return
        option_index = NUMBER_EMOJIS.index(emoji_str)
        await cast_poll_vote(poll.id, payload.member.id, option_index)


async def setup(bot: commands.Bot):
    await bot.add_cog(Polls(bot))
