"""
Voice-Aktivitäts-Tracking -- misst, wie lange Mitglieder in Sprachkanälen
verbringen.

- /voicetop      -- Bestenliste nach Sprachkanal-Zeit
- /voicezeit [member]  -- eigene oder fremde Gesamtzeit
"""
import datetime as dt

import discord
from discord.ext import commands

from bot.utils.embeds import base_embed, error_embed
from bot.utils.db_helpers import add_voice_time, get_voice_leaderboard, get_voice_time, get_guild_language

# (guild_id, user_id) -> Zeitpunkt des Beitritts zu einem Sprachkanal.
# Rein im Arbeitsspeicher -- bei Bot-Neustart geht die aktuell laufende
# Session verloren, bereits gespeicherte Gesamtzeit bleibt aber erhalten.
_voice_join_times: dict[tuple[int, int], dt.datetime] = {}


def _format_duration(total_seconds: int) -> str:
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    return f"{hours}h {minutes}m"


class VoiceTracking(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        key = (member.guild.id, member.id)

        if before.channel and not after.channel:
            joined_at = _voice_join_times.pop(key, None)
            if joined_at:
                seconds = int((dt.datetime.utcnow() - joined_at).total_seconds())
                if seconds > 0:
                    await add_voice_time(member.guild.id, member.id, seconds)

        if after.channel and not before.channel:
            _voice_join_times[key] = dt.datetime.utcnow()

    @commands.hybrid_command(name="voicetop", description="Zeigt die Bestenliste nach Sprachkanal-Zeit.")
    @commands.guild_only()
    async def voicetop(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        top = await get_voice_leaderboard(ctx.guild.id)
        if not top:
            await ctx.send(embed=error_embed("Noch keine Daten." if lang == "de" else "No data yet."))
            return
        medals = ["🥇", "🥈", "🥉"]
        lines = [f"{medals[i] if i < 3 else f'{i+1}.'} <@{e.user_id}> — {_format_duration(e.total_seconds)}"
                 for i, e in enumerate(top)]
        await ctx.send(embed=base_embed("🎙️ Voice-Bestenliste" if lang == "de" else "🎙️ Voice leaderboard", "\n".join(lines)))

    @commands.hybrid_command(name="voicezeit", description="Zeigt die Sprachkanal-Gesamtzeit eines Mitglieds.")
    @commands.guild_only()
    async def voicezeit(self, ctx: commands.Context, member: discord.Member = None):
        lang = await get_guild_language(ctx.guild.id)
        target = member or ctx.author
        seconds = await get_voice_time(ctx.guild.id, target.id)
        await ctx.send(embed=base_embed(f"🎙️ {target.display_name}", _format_duration(seconds)))


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceTracking(bot))
