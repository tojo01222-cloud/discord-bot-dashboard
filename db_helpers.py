"""
Autorole-System.

- /autorole set <ziel> <rolle>   -- richtet eine Autorole ein (SERVER_ADMIN)
- /autorole clear <ziel>         -- entfernt eine Autorole-Einrichtung (SERVER_ADMIN)
- /autorole liste                -- zeigt die aktuelle Einrichtung

Drei unabhängige Ziele (jedes kann eine eigene Rolle haben, 0 = nicht
eingerichtet):
  alle    -> wird JEDEM neuen menschlichen Mitglied beim Beitritt vergeben
  bots    -> wird JEDEM neuen Bot-/App-Account beim Beitritt vergeben
  admins  -> wird automatisch vergeben/entzogen, sobald ein Mitglied
             Administrator-Rechte bekommt bzw. verliert (egal ob direkt beim
             Beitritt oder später durch eine andere Rolle) -- praktisch, um
             Admins auf einen Blick sichtbar zu markieren (z.B. eigene Farbe),
             ohne das manuell nachpflegen zu müssen.

Vorher gab es nur EIN einzelnes Autorole-Feld ohne Unterscheidung zwischen
Mensch und Bot -- ein neu hinzugefügter Bot hätte also ungewollt dieselbe
"Willkommens"-Rolle bekommen wie ein Mensch. Das ist jetzt sauber getrennt.
"""
import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, error_embed, base_embed
from bot.utils.i18n import t
from bot.utils.db_helpers import get_guild_language, get_guild_settings_snapshot, set_autorole, AUTOROLE_TARGETS

TARGET_CHOICES = [
    app_commands.Choice(name="Alle (Menschen)", value="alle"),
    app_commands.Choice(name="Bots/Apps", value="bots"),
    app_commands.Choice(name="Administratoren", value="admins"),
]

_SNAPSHOT_KEY_BY_TARGET = {
    "alle": "autorole_id",
    "bots": "autorole_bot_id",
    "admins": "autorole_admin_id",
}


class AutoRole(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- Beitritt: alle / bots ----------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        snapshot = await get_guild_settings_snapshot(member.guild.id)
        role_id = snapshot.get("autorole_bot_id", 0) if member.bot else snapshot.get("autorole_id", 0)
        if role_id:
            role = member.guild.get_role(role_id)
            if role:
                try:
                    await member.add_roles(role, reason="Autorole")
                except discord.Forbidden:
                    pass

        # Falls das neue Mitglied (z.B. durch eine Integration) direkt beim
        # Beitritt schon Administrator-Rechte mitbringt, sofort die
        # Admin-Autorole mitgeben, statt auf die nächste Rollenänderung zu warten.
        admin_role_id = snapshot.get("autorole_admin_id", 0)
        if admin_role_id and member.guild_permissions.administrator:
            role = member.guild.get_role(admin_role_id)
            if role and role not in member.roles:
                try:
                    await member.add_roles(role, reason="Autorole: Administrator-Rechte erkannt")
                except discord.Forbidden:
                    pass

    # ---------- Admin-Rechte gewonnen/verloren ----------
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        had_admin = before.guild_permissions.administrator
        has_admin = after.guild_permissions.administrator
        if had_admin == has_admin:
            return  # keine Änderung an den Administrator-Rechten -- nichts zu tun

        snapshot = await get_guild_settings_snapshot(after.guild.id)
        admin_role_id = snapshot.get("autorole_admin_id", 0)
        if not admin_role_id:
            return
        role = after.guild.get_role(admin_role_id)
        if not role:
            return

        try:
            if has_admin and role not in after.roles:
                await after.add_roles(role, reason="Autorole: Administrator-Rechte erhalten")
            elif not has_admin and role in after.roles:
                await after.remove_roles(role, reason="Autorole: Administrator-Rechte verloren")
        except discord.Forbidden:
            pass

    # ---------- Commands ----------
    @commands.hybrid_group(name="autorole", description="Automatische Rollenvergabe verwalten.")
    @commands.guild_only()
    async def autorole(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @autorole.command(name="set", description="Richtet eine Autorole für ein Ziel ein.")
    @app_commands.describe(ziel="Für wen die Rolle automatisch vergeben wird", rolle="Die zu vergebende Rolle")
    @app_commands.choices(ziel=TARGET_CHOICES)
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def autorole_set(self, ctx: commands.Context, ziel: str, rolle: discord.Role):
        lang = await get_guild_language(ctx.guild.id)
        if ziel not in AUTOROLE_TARGETS:
            await ctx.send(embed=error_embed("Ungültiges Ziel." if lang == "de" else "Invalid target."))
            return
        if rolle >= ctx.guild.me.top_role:
            await ctx.send(embed=error_embed(
                "Diese Rolle steht höher als (oder gleich) meine eigene -- ich kann sie nicht vergeben."
                if lang == "de" else
                "That role is higher than (or equal to) my own -- I can't assign it."))
            return

        await set_autorole(ctx.guild.id, ziel, rolle.id)
        target_label = t(f"autorole.target_{ziel}", lang)
        await ctx.send(embed=success_embed(t("autorole.set", lang, target=target_label, role=rolle.mention)))

    @autorole.command(name="clear", description="Entfernt die Autorole-Einrichtung für ein Ziel.")
    @app_commands.describe(ziel="Für welches Ziel die Autorole entfernt wird")
    @app_commands.choices(ziel=TARGET_CHOICES)
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def autorole_clear(self, ctx: commands.Context, ziel: str):
        lang = await get_guild_language(ctx.guild.id)
        if ziel not in AUTOROLE_TARGETS:
            await ctx.send(embed=error_embed("Ungültiges Ziel." if lang == "de" else "Invalid target."))
            return
        await set_autorole(ctx.guild.id, ziel, 0)
        target_label = t(f"autorole.target_{ziel}", lang)
        await ctx.send(embed=success_embed(t("autorole.cleared", lang, target=target_label)))

    @autorole.command(name="liste", description="Zeigt die aktuelle Autorole-Einrichtung.")
    async def autorole_liste(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        snapshot = await get_guild_settings_snapshot(ctx.guild.id)

        lines = []
        for target in AUTOROLE_TARGETS:
            role_id = snapshot.get(_SNAPSHOT_KEY_BY_TARGET[target], 0)
            role = ctx.guild.get_role(role_id) if role_id else None
            label = t(f"autorole.target_{target}", lang)
            value = role.mention if role else ("— nicht eingerichtet —" if lang == "de" else "— not configured —")
            lines.append(f"**{label}**: {value}")

        if not any(snapshot.get(v) for v in _SNAPSHOT_KEY_BY_TARGET.values()):
            await ctx.send(embed=error_embed(t("autorole.list_empty", lang)))
            return

        embed = base_embed(t("autorole.list_title", lang))
        embed.description = "\n".join(lines)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoRole(bot))
