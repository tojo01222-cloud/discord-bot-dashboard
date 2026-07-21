"""
Einstiegspunkt des Bots.

Start: python -m bot.main   (aus dem Projekt-Hauptordner ausführen)

Neue Funktions-Module (Cogs) werden einfach als .py-Datei in bot/cogs/
abgelegt (mit `async def setup(bot): ...` am Ende) — main.py lädt sie
automatisch, ohne dass hier etwas geändert werden muss.
"""
import asyncio
import logging
import pkgutil
import datetime as dt

import discord
from discord.ext import commands, tasks

from bot.config import config
from bot.database.db import init_db, get_session
from bot.database.models import GuildSettings
from bot.utils.permissions import InsufficientPermissionError, MaintenanceModeError
from bot.utils.embeds import error_embed
from bot.utils.i18n import t
from bot.utils.db_helpers import (
    upsert_bot_guild, remove_bot_guild, get_bot_control_state,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("bot.main")

INTENTS = discord.Intents.default()
INTENTS.members = True          # nötig für Team-/Moderationssystem
INTENTS.message_content = True  # nötig für "!"-Prefix-Commands
INTENTS.voice_states = True     # nötig für Musik + Warteraum-System


class AllInOneBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=config.PREFIX,
            intents=INTENTS,
            help_command=None,  # eigener /help Command in cogs/info_help.py
        )
        # Wartungsmodus: wird über das Admin-Panel im Dashboard gesteuert
        # (separater Prozess) -- der Bot fragt das periodisch selbst ab,
        # siehe _maintenance_poll_loop() und _global_maintenance_check().
        self.maintenance_mode = False
        self.maintenance_reason = ""

    async def _global_maintenance_check(self, ctx: commands.Context) -> bool:
        if not self.maintenance_mode:
            return True
        if ctx.author.id == config.BOT_OWNER_ID:
            return True  # Bot-Owner ist nie ausgesperrt
        raise MaintenanceModeError(self.maintenance_reason)

    async def _global_blocklist_check(self, ctx: commands.Context) -> bool:
        """Sperrt Nutzer serverübergreifend von JEDEM Befehl -- läuft VOR
        jedem einzelnen Command-Aufruf, unabhängig von dessen
        Berechtigungsstufe (anders als require_level, das nur bei manchen
        Befehlen genutzt wird). Gecacht (60s TTL), damit nicht bei jedem
        einzelnen Befehlsaufruf eine Datenbankabfrage nötig ist."""
        from bot.utils.db_helpers import get_global_blocklist
        import datetime as _dt

        now = _dt.datetime.utcnow().timestamp()
        cached = getattr(self, "_blocklist_cache", None)
        if not cached or now - cached[0] > 60:
            entries = await get_global_blocklist()
            self._blocklist_cache = (now, {e.user_id for e in entries})
            cached = self._blocklist_cache

        return ctx.author.id not in cached[1]

    @tasks.loop(seconds=20)
    async def _maintenance_poll_loop(self) -> None:
        try:
            state = await get_bot_control_state()
            if state.maintenance_mode != self.maintenance_mode:
                log.info("Wartungsmodus geändert: %s (Grund: %s)", state.maintenance_mode, state.maintenance_reason)
            self.maintenance_mode = state.maintenance_mode
            self.maintenance_reason = state.maintenance_reason

            # Geplanter Wartungsmodus: automatisch starten/beenden, wenn die
            # hinterlegte Zeit erreicht ist (siehe Admin-Panel).
            from bot.utils.db_helpers import (
                get_due_maintenance_starts, get_due_maintenance_ends,
                mark_maintenance_applied, mark_maintenance_reverted, set_maintenance_mode,
            )
            now = dt.datetime.utcnow()
            for entry in await get_due_maintenance_starts(now):
                await set_maintenance_mode(True, entry.reason, 0)
                await mark_maintenance_applied(entry.id)
            for entry in await get_due_maintenance_ends(now):
                await set_maintenance_mode(False, "", 0)
                await mark_maintenance_reverted(entry.id)
        except Exception:
            log.exception("Konnte Wartungsmodus-Status nicht abfragen")

    async def load_all_cogs(self) -> None:
        import bot.cogs as cogs_package

        for module in pkgutil.iter_modules(cogs_package.__path__):
            if module.name.startswith("_"):
                continue
            extension = f"bot.cogs.{module.name}"
            try:
                await self.load_extension(extension)
                log.info("Cog geladen: %s", extension)
            except Exception:
                log.exception("Fehler beim Laden von %s", extension)

    async def setup_hook(self) -> None:
        await init_db()
        self.add_check(self._global_maintenance_check)
        self.add_check(self._global_blocklist_check)
        await self.load_all_cogs()
        synced = await self.tree.sync()
        log.info("%d Slash-Commands synchronisiert.", len(synced))
        self._maintenance_poll_loop.start()

    async def on_ready(self) -> None:
        log.info("Eingeloggt als %s (ID: %s)", self.user, self.user.id)
        log.info("Aktiv auf %d Servern.", len(self.guilds))
        for guild in self.guilds:
            await upsert_bot_guild(
                guild.id, guild.name,
                guild.icon.key if guild.icon else "",
                guild.member_count or 0,
            )

    async def on_guild_join(self, guild: discord.Guild) -> None:
        await upsert_bot_guild(guild.id, guild.name, guild.icon.key if guild.icon else "",
                                guild.member_count or 0)
        log.info("Bot wurde zu Server '%s' (%s) hinzugefügt.", guild.name, guild.id)

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        await remove_bot_guild(guild.id)
        log.info("Bot wurde von Server '%s' (%s) entfernt.", guild.name, guild.id)

    # Hinweis: Autorole-Vergabe beim Beitritt lag früher direkt hier (nur EIN
    # Ziel, ohne Unterscheidung Mensch/Bot). Jetzt vollständig in
    # bot/cogs/autorole.py, das zusätzlich Bots/Apps separat behandelt und
    # eine Administrator-Rang-Rolle automatisch synchron hält.

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        # Gilt sowohl für !prefix- als auch /slash-Aufrufe von Hybrid-Commands.
        lang = "de"
        if ctx.guild:
            async with get_session() as session:
                settings = await session.get(GuildSettings, ctx.guild.id)
                if settings:
                    lang = settings.language

        if isinstance(error, InsufficientPermissionError):
            await ctx.send(embed=error_embed(t("no_permission", lang)), ephemeral=True)
            return
        if isinstance(error, MaintenanceModeError):
            reason = f"\n{error.reason}" if error.reason else ""
            await ctx.send(embed=error_embed(
                "🔧 Wartungsmodus" if lang == "de" else "🔧 Maintenance mode",
                ("Der Bot befindet sich gerade im Wartungsmodus." if lang == "de"
                 else "The bot is currently in maintenance mode.") + reason,
            ), ephemeral=True)
            return
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send(embed=error_embed("Ungültige Eingabe" if lang == "de" else "Invalid input", str(error)),
                            ephemeral=True)
            return

        log.exception("Unbehandelter Fehler in Command '%s'", ctx.command, exc_info=error)
        try:
            from bot.utils.db_helpers import log_error
            await log_error(ctx.guild.id if ctx.guild else 0, str(ctx.command), repr(error))
        except Exception:
            pass  # Protokollierung darf den eigentlichen Fehler-Handler nie zum Absturz bringen
        await ctx.send(embed=error_embed("Fehler" if lang == "de" else "Error",
                                          "Es ist ein unerwarteter Fehler aufgetreten." if lang == "de"
                                          else "An unexpected error occurred."), ephemeral=True)


async def main() -> None:
    config.validate()
    bot = AllInOneBot()
    async with bot:
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
