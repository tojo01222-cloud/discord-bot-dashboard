"""
Level-System.

- Vergibt automatisch XP pro Nachricht (mit Cooldown gegen Spam-Farming)
- /rank [user]                      -- zeigt Level/XP
- /leaderboard                       -- Top 10 des Servers
- /levelrolle add <level> <rolle>     -- Rang-Rolle ab einem bestimmten Level (SERVER_ADMIN)
- /levelrolle list
- /levelrolle remove <id>

WICHTIGE LEKTION aus einem früheren Bug (Anti-Spam fragte bei jeder Nachricht
die Datenbank ab): der Cooldown-Check hier läuft über einen In-Memory-Cache,
NICHT über eine Datenbankabfrage bei jeder einzelnen Nachricht. Nur wenn der
Cooldown im Cache bereits abgelaufen scheint, wird überhaupt ein
Datenbank-Zugriff gemacht (und dort nochmal geprüft, als Absicherung).
"""
import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, error_embed, base_embed
from bot.utils.db_helpers import (
    get_guild_language,
    get_level_xp,
    add_xp,
    get_leaderboard,
    add_level_role_reward,
    get_level_role_rewards,
    remove_level_role_reward,
    XP_PER_LEVEL,
)

COOLDOWN_SECONDS = 60
XP_MIN, XP_MAX = 15, 25

# In-Memory-Cache: (guild_id, user_id) -> Zeitstempel der letzten XP-Vergabe.
# Verhindert, dass jede einzelne Nachricht die Datenbank abfragt.
_last_xp_time: dict[tuple[int, int], float] = {}


class Level(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        key = (message.guild.id, message.author.id)
        now = time.monotonic()
        last = _last_xp_time.get(key, 0)
        if now - last < COOLDOWN_SECONDS:
            return
        _last_xp_time[key] = now

        amount = random.randint(XP_MIN, XP_MAX)
        result = await add_xp(message.guild.id, message.author.id, amount, COOLDOWN_SECONDS)
        if result is None:
            return  # DB-seitiger Cooldown-Check hat trotzdem abgelehnt (z.B. nach Bot-Neustart)

        new_xp, new_level, leveled_up = result
        if not leveled_up:
            return

        lang = await get_guild_language(message.guild.id)
        embed = success_embed(
            "🎉 Level Up!" if lang == "de" else "🎉 Level Up!",
            f"{message.author.mention} ist jetzt **Level {new_level}**!" if lang == "de"
            else f"{message.author.mention} is now **Level {new_level}**!",
        )
        try:
            await message.channel.send(embed=embed)
        except discord.Forbidden:
            pass

        rewards = await get_level_role_rewards(message.guild.id)
        matching = [r for r in rewards if r.level == new_level]
        for reward in matching:
            role = message.guild.get_role(reward.role_id)
            if role and isinstance(message.author, discord.Member):
                try:
                    await message.author.add_roles(role, reason=f"Level {new_level} erreicht")
                except discord.Forbidden:
                    pass

    @commands.hybrid_command(name="rank", description="Zeigt dein Level und XP (oder das eines anderen Users).")
    @app_commands.describe(member="Optional: ein anderer User")
    @commands.guild_only()
    async def rank(self, ctx: commands.Context, member: discord.Member = None):
        target = member or ctx.author
        lang = await get_guild_language(ctx.guild.id)
        entry = await get_level_xp(ctx.guild.id, target.id)

        current_level_floor = entry.level * XP_PER_LEVEL
        progress = entry.xp - current_level_floor

        embed = base_embed(f"📊 {target.display_name}")
        embed.add_field(name="Level", value=str(entry.level), inline=True)
        embed.add_field(name="XP", value=f"{entry.xp} ({progress}/{XP_PER_LEVEL} bis zum nächsten Level)"
                         if lang == "de" else f"{entry.xp} ({progress}/{XP_PER_LEVEL} to next level)", inline=True)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="leaderboard", description="Zeigt die Top 10 nach XP.")
    @commands.guild_only()
    async def leaderboard(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        top = await get_leaderboard(ctx.guild.id, limit=10)
        if not top:
            await ctx.send(embed=error_embed("Noch keine Daten." if lang == "de" else "No data yet."))
            return

        embed = base_embed("🏆 Leaderboard")
        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, entry in enumerate(top):
            prefix = medals[i] if i < 3 else f"{i+1}."
            lines.append(f"{prefix} <@{entry.user_id}> — Level {entry.level} ({entry.xp} XP)")
        embed.description = "\n".join(lines)
        await ctx.send(embed=embed)

    @commands.hybrid_group(name="levelrolle", description="Rang-Rollen für Level verwalten.")
    @commands.guild_only()
    async def levelrolle(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @levelrolle.command(name="add", description="Vergibt ab einem Level automatisch eine Rolle.")
    @app_commands.describe(level="Ab diesem Level wird die Rolle vergeben", role="Die Rolle")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def levelrolle_add(self, ctx: commands.Context, level: int, role: discord.Role):
        lang = await get_guild_language(ctx.guild.id)
        await add_level_role_reward(ctx.guild.id, level, role.id)
        await ctx.send(embed=success_embed(
            "Rang-Rolle hinzugefügt" if lang == "de" else "Level role added",
            f"Ab Level {level}: {role.mention}",
        ))

    @levelrolle.command(name="list", description="Zeigt alle Rang-Rollen.")
    async def levelrolle_list(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        rewards = await get_level_role_rewards(ctx.guild.id)
        if not rewards:
            await ctx.send(embed=error_embed("Keine Rang-Rollen eingerichtet." if lang == "de"
                                              else "No level roles configured."))
            return
        embed = base_embed("🎖️ Rang-Rollen")
        lines = []
        for r in rewards:
            role = ctx.guild.get_role(r.role_id)
            lines.append(f"#{r.id} — Level {r.level} → {role.mention if role else '(gelöschte Rolle)'}")
        embed.description = "\n".join(lines)
        await ctx.send(embed=embed)

    @levelrolle.command(name="remove", description="Entfernt eine Rang-Rollen-Zuordnung.")
    @app_commands.describe(reward_id="Die ID aus /levelrolle list")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def levelrolle_remove(self, ctx: commands.Context, reward_id: int):
        lang = await get_guild_language(ctx.guild.id)
        ok = await remove_level_role_reward(reward_id)
        if ok:
            await ctx.send(embed=success_embed("Entfernt" if lang == "de" else "Removed"))
        else:
            await ctx.send(embed=error_embed("ID nicht gefunden." if lang == "de" else "ID not found."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Level(bot))
