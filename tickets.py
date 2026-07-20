"""
Level-System.

- Vergibt automatisch XP pro Nachricht (mit Cooldown gegen Spam-Farming)
- /rank [user]                      -- zeigt Level/XP mit Fortschrittsbalken und Serverrang
- /leaderboard                       -- Top 10 des Servers
- /levelrolle add <level> <rolle>     -- Rang-Rolle ab einem bestimmten Level (SERVER_ADMIN)
- /levelrolle list
- /levelrolle remove <id>
- /xp add|remove|set|reset <user>     -- XP manuell verwalten (SERVER_ADMIN)

WICHTIGE LEKTION aus einem früheren Bug (Anti-Spam fragte bei jeder Nachricht
die Datenbank ab): der Cooldown-Check hier läuft über einen In-Memory-Cache,
NICHT über eine Datenbankabfrage bei jeder einzelnen Nachricht. Nur wenn der
Cooldown im Cache bereits abgelaufen scheint, wird überhaupt ein
Datenbank-Zugriff gemacht (und dort nochmal geprüft, als Absicherung).

Bug-Fix: /xp add (oder ein sehr großer XP-Batzen) kann mehrere Level auf
einmal überspringen. Vorher wurden dabei nur Rang-Rollen für das exakt neue
Level vergeben -- alle dazwischenliegenden Level-Rollen blieben unvergeben.
Jetzt werden alle Rollen im Bereich (altes Level, neues Level] vergeben.
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
    set_level_xp,
    adjust_level_xp,
    reset_level_xp,
    XP_PER_LEVEL,
)

COOLDOWN_SECONDS = 60
XP_MIN, XP_MAX = 15, 25

# In-Memory-Cache: (guild_id, user_id) -> Zeitstempel der letzten XP-Vergabe.
# Verhindert, dass jede einzelne Nachricht die Datenbank abfragt.
_last_xp_time: dict[tuple[int, int], float] = {}


def _progress_bar(progress: int, total: int, length: int = 12) -> str:
    """Baut einen einfachen Text-Fortschrittsbalken, z.B. '█████░░░░░░░' -- rein
    optisch, damit /rank auf einen Blick verständlich ist statt nur Zahlen zu zeigen."""
    filled = max(0, min(length, round(length * progress / total))) if total else 0
    return "█" * filled + "░" * (length - filled)


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

        new_xp, new_level, old_level, leveled_up = result
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

        # Bug-Fix: vorher wurden nur Rollen für GENAU new_level vergeben. Bei
        # einem Mehrfach-Level-Sprung (z.B. durch /xp add) wurden dazwischen
        # liegende Rang-Rollen dadurch nie vergeben. Jetzt werden alle Rollen
        # für (old_level, new_level] vergeben.
        rewards = await get_level_role_rewards(message.guild.id)
        matching = [r for r in rewards if old_level < r.level <= new_level]
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
        bar = _progress_bar(progress, XP_PER_LEVEL)

        # Serverrang: Position in der vollständigen Leaderboard-Reihenfolge, nicht
        # nur unter den Top 10 -- gibt auch Usern außerhalb der Top 10 Kontext.
        full_board = await get_leaderboard(ctx.guild.id, limit=10_000)
        rank_position = next((i + 1 for i, e in enumerate(full_board) if e.user_id == target.id), None)
        rank_text = f"#{rank_position}" if rank_position else "—"

        embed = base_embed(f"📊 {target.display_name}")
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Level", value=str(entry.level), inline=True)
        embed.add_field(name="Rang" if lang == "de" else "Rank", value=rank_text, inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # Zeilenumbruch im 3er-Grid
        embed.add_field(
            name="XP",
            value=(f"{bar}\n{entry.xp} XP · {progress}/{XP_PER_LEVEL} bis zum nächsten Level" if lang == "de"
                   else f"{bar}\n{entry.xp} XP · {progress}/{XP_PER_LEVEL} to next level"),
            inline=False,
        )
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

    # ---------- XP manuell verwalten ----------
    @commands.hybrid_group(name="xp", description="XP eines Users manuell verwalten.")
    @commands.guild_only()
    async def xp(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @xp.command(name="add", description="Fügt einem User manuell XP hinzu (z.B. als Belohnung).")
    @app_commands.describe(member="Der User", betrag="Wie viel XP hinzugefügt wird")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def xp_add(self, ctx: commands.Context, member: discord.Member, betrag: int):
        await self._xp_adjust(ctx, member, betrag)

    @xp.command(name="remove", description="Zieht einem User manuell XP ab.")
    @app_commands.describe(member="Der User", betrag="Wie viel XP abgezogen wird")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def xp_remove(self, ctx: commands.Context, member: discord.Member, betrag: int):
        await self._xp_adjust(ctx, member, -abs(betrag))

    async def _xp_adjust(self, ctx: commands.Context, member: discord.Member, delta: int) -> None:
        lang = await get_guild_language(ctx.guild.id)
        old_xp, new_xp, old_level, new_level = await adjust_level_xp(ctx.guild.id, member.id, delta)

        if new_level > old_level:
            rewards = await get_level_role_rewards(ctx.guild.id)
            for reward in [r for r in rewards if old_level < r.level <= new_level]:
                role = ctx.guild.get_role(reward.role_id)
                if role:
                    try:
                        await member.add_roles(role, reason=f"XP manuell angepasst von {ctx.author}")
                    except discord.Forbidden:
                        pass

        sign = "+" if delta >= 0 else ""
        await ctx.send(embed=success_embed(
            "XP angepasst" if lang == "de" else "XP adjusted",
            f"{member.mention}: {old_xp} → {new_xp} XP ({sign}{delta}), Level {old_level} → {new_level}",
        ))

    @xp.command(name="set", description="Setzt die XP eines Users auf einen festen Wert.")
    @app_commands.describe(member="Der User", betrag="Der neue XP-Wert")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def xp_set(self, ctx: commands.Context, member: discord.Member, betrag: int):
        lang = await get_guild_language(ctx.guild.id)
        if betrag < 0:
            await ctx.send(embed=error_embed("Der XP-Wert darf nicht negativ sein." if lang == "de"
                                              else "XP value can't be negative."))
            return
        new_xp, new_level = await set_level_xp(ctx.guild.id, member.id, betrag)
        await ctx.send(embed=success_embed(
            "XP gesetzt" if lang == "de" else "XP set",
            f"{member.mention}: {new_xp} XP, Level {new_level}",
        ))

    @xp.command(name="reset", description="Setzt die XP und das Level eines Users auf 0 zurück.")
    @app_commands.describe(member="Der User")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def xp_reset(self, ctx: commands.Context, member: discord.Member):
        lang = await get_guild_language(ctx.guild.id)
        await reset_level_xp(ctx.guild.id, member.id)
        await ctx.send(embed=success_embed(
            "Zurückgesetzt" if lang == "de" else "Reset",
            f"{member.mention}: 0 XP, Level 0",
        ))


async def setup(bot: commands.Bot):
    await bot.add_cog(Level(bot))
