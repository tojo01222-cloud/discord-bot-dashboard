"""
Server-Backup -- speichert einen Snapshot der aktuellen Rollen und Kanäle.

- /backup_erstellen    -- erstellt einen neuen Snapshot (SERVER_ADMIN)
- /backup_liste          -- zeigt vorhandene Snapshots mit Zeitstempel

BEWUSST keine automatische "Restore"-Funktion: das automatische Löschen/
Neuanlegen von Rollen und Kanälen ist hochriskant (falsch angewendet
zerstört es den Server) und gehört nicht in einen Ein-Klick-Befehl. Der
Snapshot dient als Dokumentation/Notfall-Referenz, die ein Admin im
Zweifel manuell zum Wiederherstellen nutzt.
"""
import json

from discord.ext import commands

from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, error_embed, base_embed
from bot.utils.db_helpers import get_guild_language, create_server_backup, get_server_backups


class ServerBackup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="backup_erstellen", description="Erstellt einen Snapshot der aktuellen Rollen und Kanäle.")
    @commands.guild_only()
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def backup_erstellen(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        snapshot = {
            "roles": [{"name": r.name, "id": r.id, "position": r.position, "color": str(r.color)}
                      for r in ctx.guild.roles],
            "channels": [{"name": c.name, "id": c.id, "type": str(c.type),
                          "category": c.category.name if c.category else None}
                         for c in ctx.guild.channels],
        }
        backup = await create_server_backup(ctx.guild.id, snapshot, ctx.author.id)
        await ctx.send(embed=success_embed(
            f"📦 Backup #{backup.id} erstellt ({len(snapshot['roles'])} Rollen, "
            f"{len(snapshot['channels'])} Kanäle)." if lang == "de" else
            f"📦 Backup #{backup.id} created ({len(snapshot['roles'])} roles, "
            f"{len(snapshot['channels'])} channels)."))

    @commands.hybrid_command(name="backup_liste", description="Zeigt vorhandene Server-Backups.")
    @commands.guild_only()
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def backup_liste(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        backups = await get_server_backups(ctx.guild.id)
        if not backups:
            await ctx.send(embed=error_embed("Noch keine Backups vorhanden." if lang == "de" else "No backups yet."))
            return
        lines = []
        for b in backups[:15]:
            snapshot = json.loads(b.snapshot_json)
            lines.append(f"#{b.id} — {b.created_at.strftime('%d.%m.%Y %H:%M')} — "
                         f"{len(snapshot['roles'])} Rollen, {len(snapshot['channels'])} Kanäle")
        await ctx.send(embed=base_embed("📦 Server-Backups", "\n".join(lines)))


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerBackup(bot))
