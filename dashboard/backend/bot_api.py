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
