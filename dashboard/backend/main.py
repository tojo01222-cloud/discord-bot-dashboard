"""
Dashboard-Backend (Phase 4 — Basis).
Laeuft als eigener Prozess, getrennt vom Bot (siehe README).
"""
import secrets

from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from dashboard.backend.config import dashboard_config as cfg
from dashboard.backend import discord_oauth
from dashboard.backend.bot_api import fetch_guild_text_channels
from bot.database.db import init_db, get_session
from bot.utils.db_helpers import (
    upsert_dashboard_user,
    get_bot_guild_ids,
    save_guild_settings_from_dashboard,
    get_or_create_guild_settings,
)

app = FastAPI(title="Bot Dashboard")
app.add_middleware(SessionMiddleware, secret_key=cfg.SESSION_SECRET, same_site="lax")
app.mount("/static", StaticFiles(directory="dashboard/backend/static"), name="static")
templates = Jinja2Templates(directory="dashboard/backend/templates")


@app.on_event("startup")
async def on_startup():
    cfg.validate()
    await init_db()


def _current_user(request: Request):
    return request.session.get("user")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if _current_user(request):
        return RedirectResponse("/servers")
    return templates.TemplateResponse(request, "login.html", {"user": None, "messages": []})


@app.get("/datenschutz", response_class=HTMLResponse)
async def datenschutz(request: Request):
    return templates.TemplateResponse(request, "datenschutz.html", {
        "user": _current_user(request), "messages": [],
    })


@app.get("/login")
async def login(request: Request):
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    return RedirectResponse(discord_oauth.build_authorize_url(state))


@app.get("/auth/callback")
async def auth_callback(request: Request, code: str = "", state: str = ""):
    expected_state = request.session.get("oauth_state")
    if not code or not state or state != expected_state:
        return RedirectResponse("/?error=invalid_state")

    token_data = await discord_oauth.exchange_code(code)
    access_token = token_data["access_token"]

    discord_user = await discord_oauth.fetch_user(access_token)
    dashboard_user = await upsert_dashboard_user(
        discord_id=int(discord_user["id"]),
        username=discord_user["username"],
        avatar_hash=discord_user.get("avatar") or "",
    )

    request.session["user"] = {
        "discord_id": discord_user["id"],
        "username": discord_user["username"],
        "avatar_hash": discord_user.get("avatar") or "",
        "dashboard_id": dashboard_user.id,
    }
    request.session["access_token"] = access_token
    return RedirectResponse("/servers")


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")


@app.get("/servers", response_class=HTMLResponse)
async def servers(request: Request):
    user = _current_user(request)
    if not user:
        return RedirectResponse("/")

    access_token = request.session.get("access_token", "")
    user_guilds = await discord_oauth.fetch_user_guilds(access_token)
    bot_guild_ids = await get_bot_guild_ids()

    manageable = []
    for g in user_guilds:
        if not discord_oauth.can_manage_guild(g["permissions"]):
            continue
        manageable.append({
            "id": g["id"],
            "name": g["name"],
            "icon": g.get("icon"),
            "bot_present": int(g["id"]) in bot_guild_ids,
        })

    invite_url = (
        f"https://discord.com/oauth2/authorize?client_id={cfg.DISCORD_CLIENT_ID}"
        f"&permissions=8&scope=bot%20applications.commands"
    )

    return templates.TemplateResponse(request, "guilds.html", {
        "user": user, "messages": [],
        "manageable_guilds": manageable, "invite_url": invite_url,
    })


async def _require_guild_access(request: Request, guild_id: int):
    user = _current_user(request)
    if not user:
        return RedirectResponse("/")

    bot_guild_ids = await get_bot_guild_ids()
    if guild_id not in bot_guild_ids:
        return RedirectResponse("/servers?error=bot_not_present")

    access_token = request.session.get("access_token", "")
    user_guilds = await discord_oauth.fetch_user_guilds(access_token)
    match = next((g for g in user_guilds if int(g["id"]) == guild_id), None)
    if not match or not discord_oauth.can_manage_guild(match["permissions"]):
        return RedirectResponse("/servers?error=no_access")

    return None


@app.get("/dashboard/{guild_id}", response_class=HTMLResponse)
async def guild_settings_page(request: Request, guild_id: int):
    denied = await _require_guild_access(request, guild_id)
    if denied:
        return denied

    user = _current_user(request)
    async with get_session() as session:
        settings = await get_or_create_guild_settings(session, guild_id)

    text_channels = await fetch_guild_text_channels(guild_id)

    access_token = request.session.get("access_token", "")
    user_guilds = await discord_oauth.fetch_user_guilds(access_token)
    match = next((g for g in user_guilds if int(g["id"]) == guild_id), {"name": f"Server {guild_id}"})

    return templates.TemplateResponse(request, "settings.html", {
        "user": user, "messages": [],
        "guild": {"id": guild_id, "name": match["name"]},
        "settings": settings,
        "text_channels": text_channels,
    })


@app.post("/dashboard/{guild_id}/settings")
async def save_guild_settings(
    request: Request, guild_id: int,
    language: str = Form("de"),
    mod_log_channel_id: int = Form(0),
    punishment_log_channel_id: int = Form(0),
    announcement_channel_id: int = Form(0),
):
    denied = await _require_guild_access(request, guild_id)
    if denied:
        return denied

    await save_guild_settings_from_dashboard(
        guild_id, language, mod_log_channel_id, punishment_log_channel_id, announcement_channel_id,
    )
    return RedirectResponse(f"/dashboard/{guild_id}?saved=1", status_code=303)
