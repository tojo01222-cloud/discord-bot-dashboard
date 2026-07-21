"""
Server-Aktivitätsstatistik (fürs Dashboard-Diagramm) + Rollen-Menü
(Self-Service Rollen per Button, ohne Reaction).

Aktivitäts-Zählung ist bewusst NICHT pro Nachricht einzeln in der Datenbank
gespeichert (wäre wieder der Anti-Spam-Performance-Fehler) -- stattdessen
wird in einem einfachen Zähler im Arbeitsspeicher gesammelt und alle
5 Minuten gebündelt in die Datenbank geschrieben.

- /rollenmenue erstellen <titel> <rollen...>   -- postet ein Rollen-Menü (SERVER_ADMIN)
"""
import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, error_embed
from bot.utils.db_helpers import increment_daily_activity, get_guild_language

ROLE_MENU_CUSTOM_ID = "rolemenu_select_dynamic"

_message_counts: dict[int, int] = {}
_join_counts: dict[int, int] = {}


class RoleMenuSelect(discord.ui.Select):
    def __init__(self, roles: list[discord.Role] | None = None):
        # Ohne roles (z.B. beim Wiederherstellen nach einem Neustart) wird ein
        # Platzhalter verwendet -- die eigentliche Nachricht behält ihre echten
        # Optionen, nur diese Instanz hier dient dem persistenten Dispatcher.
        options = (
            [discord.SelectOption(label=r.name, value=str(r.id)) for r in roles[:25]]
            if roles else [discord.SelectOption(label="—", value="0")]
        )
        super().__init__(
            placeholder="Rolle(n) wählen...", min_values=0, max_values=len(options),
            options=options, custom_id=ROLE_MENU_CUSTOM_ID,
        )

    async def callback(self, interaction: discord.Interaction):
        # Bewusst nur HINZUFÜGEN, kein Entfernen: nach einem Bot-Neustart kennt
        # diese Dispatcher-Instanz nicht mehr alle ursprünglichen Optionen der
        # jeweiligen Nachricht -- "nur hinzufügen" bleibt dadurch immer korrekt,
        # "entfernen" könnte sonst versehentlich falsche Rollen betreffen.
        member = interaction.user
        guild = interaction.guild
        added = []
        for value in self.values:
            if value == "0":
                continue
            role = guild.get_role(int(value))
            if role and role < guild.me.top_role and role not in member.roles:
                try:
                    await member.add_roles(role, reason="Rollen-Menü")
                    added.append(role.name)
                except discord.Forbidden:
                    pass

        text = f"✅ Rollen hinzugefügt: {', '.join(added)}" if added else "ℹ️ Keine neuen Rollen hinzugefügt."
        await interaction.response.send_message(text, ephemeral=True)


class RoleMenuView(discord.ui.View):
    def __init__(self, roles: list[discord.Role] | None = None):
        super().__init__(timeout=None)
        self.add_item(RoleMenuSelect(roles))


class ActivityRoleMenu(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(RoleMenuView())  # persistenter Dispatcher, siehe RoleMenuSelect-Docstring
        self._flush_loop.start()

    def cog_unload(self) -> None:
        self._flush_loop.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        _message_counts[message.guild.id] = _message_counts.get(message.guild.id, 0) + 1

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        _join_counts[member.guild.id] = _join_counts.get(member.guild.id, 0) + 1

    @tasks.loop(minutes=5)
    async def _flush_loop(self) -> None:
        today = dt.datetime.utcnow().strftime("%Y-%m-%d")
        guild_ids = set(_message_counts.keys()) | set(_join_counts.keys())
        for guild_id in guild_ids:
            messages = _message_counts.pop(guild_id, 0)
            joins = _join_counts.pop(guild_id, 0)
            if messages or joins:
                await increment_daily_activity(guild_id, today, messages=messages, joins=joins)

    @_flush_loop.before_loop
    async def _before_flush(self) -> None:
        await self.bot.wait_until_ready()

    @commands.hybrid_group(name="rollenmenue", description="Self-Service-Rollenmenü verwalten.")
    @commands.guild_only()
    async def rollenmenue(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @rollenmenue.command(name="erstellen", description="Postet ein Rollen-Menü zum Selbstauswählen (bis zu 5 Rollen).")
    @app_commands.describe(
        titel="Titel des Menüs", rolle1="1. Rolle", rolle2="2. Rolle (optional)",
        rolle3="3. Rolle (optional)", rolle4="4. Rolle (optional)", rolle5="5. Rolle (optional)",
    )
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def rollenmenue_erstellen(self, ctx: commands.Context, titel: str, rolle1: discord.Role,
                                     rolle2: discord.Role = None, rolle3: discord.Role = None,
                                     rolle4: discord.Role = None, rolle5: discord.Role = None):
        lang = await get_guild_language(ctx.guild.id)
        roles = [r for r in [rolle1, rolle2, rolle3, rolle4, rolle5] if r is not None]

        embed = success_embed(f"🎭 {titel}", "Wähle deine Rollen im Menü unten aus." if lang == "de"
                               else "Choose your roles from the menu below.")
        await ctx.send(embed=embed, view=RoleMenuView(roles))


async def setup(bot: commands.Bot):
    await bot.add_cog(ActivityRoleMenu(bot))
