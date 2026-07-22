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


async def fetch_guild_channels_categorized(guild_id: int) -> dict:
    """Holt die Kanalliste EINMAL und sortiert sie lokal in Text/Voice/Kategorien
    -- spart 2 von 3 komplett identischen API-Aufrufen gegenüber dem separaten
    Aufruf von fetch_guild_text_channels/fetch_guild_voice_channels/
    fetch_guild_categories (alle drei fragten bisher dieselbe Adresse ab).
    Für Seiten, die mehrere Kanal-Typen gleichzeitig brauchen (z.B. die
    Einstellungsseite), deutlich schneller."""
    if not DISCORD_TOKEN:
        return {"text": [], "voice": [], "categories": []}
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{cfg.DISCORD_API_BASE}/guilds/{guild_id}/channels", headers=headers)
        if resp.status_code != 200:
            return {"text": [], "voice": [], "categories": []}
        channels = resp.json()
        return {
            "text": [c for c in channels if c.get("type") == TEXT_CHANNEL_TYPE],
            "voice": [c for c in channels if c.get("type") == VOICE_CHANNEL_TYPE],
            "categories": [c for c in channels if c.get("type") == CATEGORY_CHANNEL_TYPE],
        }


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
        success = resp.status_code == 200
        await _track_api_call(success)
        return success


async def _track_api_call(success: bool) -> None:
    """Zählt Erfolg/Fehlschlag fürs Admin-Panel-API-Statistik-Diagramm.
    Bewusst nur an den am häufigsten genutzten Stellen eingebaut (Broadcast,
    Server-Verlassen), nicht an jedem einzelnen der vielen bot_api.py-Aufrufe --
    das würde den Umfang sprengen, reicht für einen repräsentativen Trend."""
    try:
        import datetime as _dt
        from bot.utils.db_helpers import record_api_call
        await record_api_call(_dt.datetime.utcnow().strftime("%Y-%m-%d"), success)
    except Exception:
        pass  # Statistik darf den eigentlichen API-Aufruf nie zum Absturz bringen


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


async def fetch_guild_members(guild_id: int, limit: int = 1000) -> list[dict]:
    """Holt ALLE Mitglieder eines Servers (paginiert, Discord liefert max.
    1000 pro Aufruf) -- fürs Dashboard-"Autorole an alle vergeben"."""
    if not DISCORD_TOKEN:
        return []
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    members: list[dict] = []
    after = "0"
    async with httpx.AsyncClient() as client:
        while True:
            resp = await client.get(
                f"{cfg.DISCORD_API_BASE}/guilds/{guild_id}/members",
                headers=headers, params={"limit": 1000, "after": after},
            )
            if resp.status_code != 200:
                break
            batch = resp.json()
            if not batch:
                break
            members.extend(batch)
            if len(batch) < 1000 or len(members) >= limit:
                break
            after = batch[-1]["user"]["id"]
    return members


async def add_role_to_member(guild_id: int, user_id: int, role_id: int, reason: str = "") -> bool:
    if not DISCORD_TOKEN:
        return False
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}", "X-Audit-Log-Reason": reason[:400]}
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{cfg.DISCORD_API_BASE}/guilds/{guild_id}/members/{user_id}/roles/{role_id}", headers=headers,
        )
        return resp.status_code in (200, 204)


async def create_guild_role(guild_id: int, name: str, color: int = 0) -> bool:
    """Erstellt eine neue Rolle auf einem Server -- fürs Anwenden von
    Rollen-Vorlagen (siehe /admin/rollen-vorlagen)."""
    if not DISCORD_TOKEN:
        return False
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{cfg.DISCORD_API_BASE}/guilds/{guild_id}/roles", headers=headers,
            json={"name": name, "color": color},
        )
        return resp.status_code == 200


async def send_ticket_button_panel(channel_id: int, embed: dict, custom_id: str,
                                    button_label: str, button_emoji: str) -> bool:
    """Sendet ein Ticket-Panel mit EINEM Button (neues, vereinfachtes System --
    ersetzt das alte Auswahlmenü mit mehreren Ticket-Arten). Funktioniert per
    REST, ohne dass das Dashboard selbst mit dem Discord-Gateway verbunden ist:
    der custom_id 'ticket_panel_create_<id>' wird im Bot-Prozess über einen
    generischen on_interaction-Dispatcher abgefangen (siehe bot/cogs/tickets.py)."""
    if not DISCORD_TOKEN:
        return False
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    components = [{
        "type": 1,  # Action Row
        "components": [{
            "type": 2,  # Button
            "style": 1,  # Primary
            "custom_id": custom_id,
            "label": button_label,
            "emoji": {"name": button_emoji},
        }],
    }]
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{cfg.DISCORD_API_BASE}/channels/{channel_id}/messages",
            headers=headers, json={"embeds": [embed], "components": components},
        )
        return resp.status_code == 200


async def send_channel_embed_get_id(channel_id: int, embed: dict) -> int | None:
    """Wie send_channel_message, aber mit Embed statt reinem Text -- gibt die
    neue Nachrichten-ID zurück (z.B. um danach Reaktionen hinzuzufügen)."""
    if not DISCORD_TOKEN:
        return None
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{cfg.DISCORD_API_BASE}/channels/{channel_id}/messages",
            headers=headers, json={"embeds": [embed]},
        )
        if resp.status_code != 200:
            return None
        return int(resp.json()["id"])


async def add_message_reaction(channel_id: int, message_id: int, emoji: str) -> bool:
    if not DISCORD_TOKEN:
        return False
    import urllib.parse
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    encoded_emoji = urllib.parse.quote(emoji)
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{cfg.DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}/@me",
            headers=headers,
        )
        return resp.status_code in (200, 204)
