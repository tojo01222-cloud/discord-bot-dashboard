"""
Discord OAuth2 "Authorization Code Grant" — der Standard-Login-Flow.

Ablauf:
1. build_authorize_url()   -> User wird zu Discord geschickt, bestätigt dort den Zugriff
2. Discord leitet zurück zu DISCORD_REDIRECT_URI mit einem einmaligen "code"
3. exchange_code()          -> tauscht den Code gegen ein Access-Token
4. fetch_user()              -> holt die Discord-Profildaten des eingeloggten Users
5. fetch_user_guilds()        -> holt die Serverliste des Users (um zu wissen, wo er Admin ist)

Wichtig: der Access-Token gehört dem EINGELOGGTEN USER, nicht dem Bot — er
erlaubt nur, Daten über diesen einen User abzufragen, keine Server-Verwaltung.
Die eigentliche Serververwaltung läuft über den Bot-Token in bot/, nicht hier.
"""
from urllib.parse import urlencode

import httpx

from dashboard.backend.config import dashboard_config as cfg

PERMISSION_MANAGE_GUILD = 0x20
PERMISSION_ADMINISTRATOR = 0x8


def build_authorize_url(state: str) -> str:
    params = {
        "client_id": cfg.DISCORD_CLIENT_ID,
        "redirect_uri": cfg.DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": cfg.OAUTH_SCOPES,
        "state": state,
        "prompt": "consent",
    }
    return f"{cfg.DISCORD_API_BASE}/oauth2/authorize?{urlencode(params)}"


async def exchange_code(code: str) -> dict:
    data = {
        "client_id": cfg.DISCORD_CLIENT_ID,
        "client_secret": cfg.DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": cfg.DISCORD_REDIRECT_URI,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{cfg.DISCORD_API_BASE}/oauth2/token", data=data, headers=headers)
        resp.raise_for_status()
        return resp.json()  # enthält access_token, refresh_token, expires_in, ...


async def fetch_user(access_token: str) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{cfg.DISCORD_API_BASE}/users/@me", headers=headers)
        resp.raise_for_status()
        return resp.json()  # id, username, avatar, ...


async def fetch_user_guilds(access_token: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{cfg.DISCORD_API_BASE}/users/@me/guilds", headers=headers)
        resp.raise_for_status()
        return resp.json()  # Liste von {id, name, icon, permissions, ...}


def can_manage_guild(permissions: str | int) -> bool:
    """Discord liefert 'permissions' als String einer großen Zahl (Bitfeld)."""
    bits = int(permissions)
    return bool(bits & PERMISSION_ADMINISTRATOR) or bool(bits & PERMISSION_MANAGE_GUILD)
