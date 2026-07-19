"""
Zentrales Berechtigungssystem.

Ziel: EIN Ort, an dem festgelegt wird, wer was darf — statt in jedem
einzelnen Command manuell Rollen abzufragen. Das macht es später leicht,
über das Web-Dashboard (Phase 8) einstellbar zu machen, welche Rolle
welchen Befehl ausführen darf, ohne den Bot-Code anzufassen.

Berechtigungsstufen (aufsteigend):
    EVERYONE        -> jeder
    TEAM             -> Team-Mitglied (irgendein definierter Team-Rang)
    MODERATOR        -> Team-Rang mit Moderationsrechten
    SERVER_ADMIN      -> Discord "Administrator"-Rechte auf dem Server
    BOT_OWNER         -> nur der Discord-Account aus BOT_OWNER_ID (config)
"""
from __future__ import annotations

from enum import IntEnum

import discord
from discord.ext import commands

from bot.config import config


class InsufficientPermissionError(commands.CheckFailure):
    """Wird ausgelöst, wenn ein User die nötige PermissionLevel nicht erreicht."""

    def __init__(self, required: "PermissionLevel"):
        self.required = required
        super().__init__(f"Benötigte Berechtigungsstufe: {required.name}")


class MaintenanceModeError(commands.CheckFailure):
    """Wird ausgelöst, wenn der Bot über das Admin-Panel in den Wartungsmodus
    versetzt wurde (siehe bot/main.py, dashboard admin_routes.py)."""

    def __init__(self, reason: str = ""):
        self.reason = reason
        super().__init__("Bot ist im Wartungsmodus")


class PermissionLevel(IntEnum):
    EVERYONE = 0
    TEAM = 1
    MODERATOR = 2
    SERVER_ADMIN = 3
    BOT_OWNER = 4


def get_member_permission_level(member: discord.Member) -> PermissionLevel:
    """
    Ermittelt die höchste Berechtigungsstufe eines Members.
    TEAM/MODERATOR werden aktuell über Discord-Berechtigungen abgeleitet
    (kick_members / manage_roles); in Phase 2 wird das zusätzlich mit der
    TeamRank-Tabelle aus der Datenbank verknüpft (feingranularer, pro Rang).
    """
    if member.id == config.BOT_OWNER_ID:
        return PermissionLevel.BOT_OWNER

    perms = member.guild_permissions
    if perms.administrator:
        return PermissionLevel.SERVER_ADMIN
    if perms.kick_members or perms.ban_members or perms.moderate_members:
        return PermissionLevel.MODERATOR
    if perms.manage_roles or perms.manage_messages:
        return PermissionLevel.TEAM

    return PermissionLevel.EVERYONE


def require_level(min_level: PermissionLevel):
    """
    Decorator für Hybrid-Commands (funktioniert für /befehl UND !befehl gleichermaßen), z.B.:

        @commands.hybrid_command(...)
        @require_level(PermissionLevel.SERVER_ADMIN)
        async def ban(self, ctx: commands.Context, ...):
            ...

    Wichtig: dieser Decorator muss UNTER @commands.hybrid_command stehen (also danach
    geschrieben werden), das ist die normale discord.py-Reihenfolge für Checks.
    """

    async def predicate(ctx: commands.Context) -> bool:
        if not isinstance(ctx.author, discord.Member):
            return False
        level = get_member_permission_level(ctx.author)
        if level >= min_level:
            return True
        raise InsufficientPermissionError(min_level)

    return commands.check(predicate)
