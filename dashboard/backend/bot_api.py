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
