"""
Aufrufe an die Discord-API mit dem BOT-Token (nicht dem User-OAuth-Token aus
discord_oauth.py). Wird gebraucht, um z.B. die Textkanäle eines Servers für
die Einstellungen-Dropdowns zu laden — das kann der User-Token nicht, dafür
braucht es die Bot-Berechtigungen.
"""
import os

import httpx

from dashboard.backend.config import dashboard_config as cfg

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")

TEXT_CHANNEL_TYPE = 0  # Discord Channel-Type-ID für normale Textkanäle
VOICE_CHANNEL_TYPE = 2
CATEGORY_CHANNEL_TYPE = 4


async def fetch_guild_text_channels(guild_id: int) -> list[dict]:
    if not DISCORD_TOKEN:
        return []
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{cfg.DISCORD_API_BASE}/guilds/{guild_id}/channels", headers=headers)
        if resp.status_code != 200:
            return []
        channels = resp.json()
        return [c for c in channels if c.get("type") == TEXT_CHANNEL_TYPE]


async def fetch_guild_voice_channels(guild_id: int) -> list[dict]:
    if not DISCORD_TOKEN:
        return []
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{cfg.DISCORD_API_BASE}/guilds/{guild_id}/channels", headers=headers)
        if resp.status_code != 200:
            return []
        channels = resp.json()
        return [c for c in channels if c.get("type") == VOICE_CHANNEL_TYPE]


async def fetch_guild_categories(guild_id: int) -> list[dict]:
    if not DISCORD_TOKEN:
        return []
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{cfg.DISCORD_API_BASE}/guilds/{guild_id}/channels", headers=headers)
        if resp.status_code != 200:
            return []
        channels = resp.json()
        return [c for c in channels if c.get("type") == CATEGORY_CHANNEL_TYPE]


async def fetch_guild_roles(guild_id: int) -> list[dict]:
    if not DISCORD_TOKEN:
        return []
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{cfg.DISCORD_API_BASE}/guilds/{guild_id}/roles", headers=headers)
        if resp.status_code != 200:
            return []
        roles = resp.json()
        # @everyone-Rolle (id == guild_id) und Bot-eigene Rollen rausfiltern -- ergibt keinen Sinn als Autorole
        return [r for r in roles if r["id"] != str(guild_id) and not r.get("managed")]


async def send_channel_message(channel_id: int, content: str) -> bool:
    """Sendet eine Nachricht über den BOT-Token in einen Kanal (fürs Admin-Panel:
    globale Ankündigungen). Gibt True/False zurück, ob es geklappt hat."""
    if not DISCORD_TOKEN:
        return False
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{cfg.DISCORD_API_BASE}/channels/{channel_id}/messages",
            headers=headers, json={"content": content},
        )
        return resp.status_code == 200


async def create_guild_invite(guild_id: int) -> str | None:
    """Erzeugt einen Einladungslink für einen Server, über den ersten
    erreichbaren Textkanal (fürs Admin-Panel: Server-Übersicht)."""
    channels = await fetch_guild_text_channels(guild_id)
    if not channels:
        return None
    channel_id = channels[0]["id"]
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{cfg.DISCORD_API_BASE}/channels/{channel_id}/invites",
            headers=headers, json={"max_age": 86400, "max_uses": 0},
        )
        if resp.status_code != 200:
            return None
        code = resp.json().get("code")
        return f"https://discord.gg/{code}" if code else None


async def leave_guild(guild_id: int) -> bool:
    """Lässt den Bot einen Server verlassen (Admin-Panel-Funktion)."""
    if not DISCORD_TOKEN:
        return False
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    async with httpx.AsyncClient() as client:
        resp = await client.delete(f"{cfg.DISCORD_API_BASE}/users/@me/guilds/{guild_id}", headers=headers)
        return resp.status_code in (200, 204)


async def kick_member(guild_id: int, user_id: int, reason: str) -> bool:
    if not DISCORD_TOKEN:
        return False
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}", "X-Audit-Log-Reason": reason[:400]}
    async with httpx.AsyncClient() as client:
        resp = await client.delete(f"{cfg.DISCORD_API_BASE}/guilds/{guild_id}/members/{user_id}", headers=headers)
        return resp.status_code in (200, 204)


async def ban_member(guild_id: int, user_id: int, reason: str) -> bool:
    if not DISCORD_TOKEN:
        return False
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}", "X-Audit-Log-Reason": reason[:400]}
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{cfg.DISCORD_API_BASE}/guilds/{guild_id}/bans/{user_id}", headers=headers, json={},
        )
        return resp.status_code in (200, 204)
