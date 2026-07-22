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


async def set_channel_slowmode(channel_id: int, seconds: int) -> bool:
    if not DISCORD_TOKEN:
        return False
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{cfg.DISCORD_API_BASE}/channels/{channel_id}", headers=headers,
            json={"rate_limit_per_user": seconds},
        )
        return resp.status_code == 200


async def set_channel_lock(guild_id: int, channel_id: int, locked: bool) -> bool:
    """Sperrt/entsperrt einen Kanal für @everyone (send_messages=False bzw.
    zurück auf Server-Standard). WICHTIG: die Discord-API ersetzt bei einem
    PUT die KOMPLETTE Berechtigung für ein Ziel, nicht nur ein einzelnes Bit
    -- deshalb erst die bestehenden allow/deny-Werte abfragen und nur das
    SEND_MESSAGES-Bit (1<<11) gezielt ändern, statt versehentlich alle
    anderen bereits gesetzten Berechtigungen für @everyone zu löschen."""
    if not DISCORD_TOKEN:
        return False
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    send_messages_bit = 1 << 11

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{cfg.DISCORD_API_BASE}/channels/{channel_id}", headers=headers)
        if resp.status_code != 200:
            return False
        channel_data = resp.json()

        existing_allow, existing_deny = 0, 0
        for overwrite in channel_data.get("permission_overwrites", []):
            if overwrite.get("id") == str(guild_id) and overwrite.get("type") == 0:
                existing_allow = int(overwrite.get("allow", 0))
                existing_deny = int(overwrite.get("deny", 0))
                break

        if locked:
            new_deny = existing_deny | send_messages_bit
            new_allow = existing_allow & ~send_messages_bit
        else:
            new_deny = existing_deny & ~send_messages_bit
            new_allow = existing_allow  # nicht explizit erlauben, nur die Sperre aufheben

        put_resp = await client.put(
            f"{cfg.DISCORD_API_BASE}/channels/{channel_id}/permissions/{guild_id}",
            headers=headers, json={"allow": str(new_allow), "deny": str(new_deny), "type": 0},
        )
        return put_resp.status_code in (200, 204)


async def set_member_nickname(guild_id: int, user_id: int, nickname: str) -> bool:
    if not DISCORD_TOKEN:
        return False
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{cfg.DISCORD_API_BASE}/guilds/{guild_id}/members/{user_id}", headers=headers,
            json={"nick": nickname or None},
        )
        return resp.status_code == 200

async def send_ticket_panel(guild_id: int, channel_id: int, design: str = "standard") -> bool:
    """Sendet das Ticket-Panel (Embed + Dropdown/Button) direkt per Discord-REST-API
    -- braucht dafür NICHT den Bot-Prozess, da wir schon den Bot-Token haben.
    custom_id "ticket_type_select" bzw. "ticket_create_button" matcht exakt die
    IDs, auf die bot/cogs/tickets.py als persistente Views lauscht."""
    from bot.utils.db_helpers import get_ticket_categories, count_open_tickets_by_category

    if not DISCORD_TOKEN:
        return False

    categories = await get_ticket_categories(guild_id)

    design_colors = {"standard": 0x5865F2, "minimal": 0x99AAB5, "premium": 0xF1C40F, "dark": 0x1E1E28}
    design_emojis = {"standard": "🎫", "minimal": "✉️", "premium": "⭐", "dark": "🌑"}
    color = design_colors.get(design, design_colors["standard"])
    emoji = design_emojis.get(design, "🎫")

    fields = []
    if categories:
        lines = []
        for c in categories[:25]:
            line = f"{c.emoji} **{c.name}**"
            if c.description:
                line += f"\n> {c.description}"
            if c.max_concurrent:
                open_count = await count_open_tickets_by_category(c.id)
                available = max(0, c.max_concurrent - open_count)
                line += f"\n> Verfügbar: {available}/{c.max_concurrent}"
            lines.append(line)
        fields.append({"name": "📂 Verfügbare Setups", "value": "\n".join(lines), "inline": False})
    if design == "premium":
        fields.append({"name": "✨ Was dich erwartet",
                        "value": "Ein privater Kanal nur für dich und unser Team.", "inline": False})

    embed = {
        "title": f"{emoji} Support-Ticket",
        "description": "Klicke unten, um ein Ticket zu erstellen.\n" + ("─" * 28),
        "color": color,
        "fields": fields,
        "footer": {"text": "Support-Team"},
    }

    if categories:
        options = []
        for c in categories[:25]:
            opt = {"label": c.name[:100], "value": str(c.id)}
            if c.description:
                opt["description"] = c.description[:100]
            if c.emoji:
                opt["emoji"] = {"name": c.emoji}
            options.append(opt)
        components = [{"type": 1, "components": [{
            "type": 3, "custom_id": "ticket_type_select", "placeholder": "…",
            "min_values": 1, "max_values": 1, "options": options,
        }]}]
    else:
        components = [{"type": 1, "components": [{
            "type": 2, "style": 1, "label": "Ticket erstellen",
            "emoji": {"name": "🎫"}, "custom_id": "ticket_create_button",
        }]}]

    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{cfg.DISCORD_API_BASE}/channels/{channel_id}/messages",
            headers=headers, json={"embeds": [embed], "components": components},
        )
    return resp.status_code == 200
