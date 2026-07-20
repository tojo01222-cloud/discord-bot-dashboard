"""
Dashboard-Backend (Phase 4 — Basis).
Laeuft als eigener Prozess, getrennt vom Bot (siehe README).
"""
import logging
import secrets

import httpx
from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from dashboard.backend.config import dashboard_config as cfg
from dashboard.backend import discord_oauth
from dashboard.backend.bot_api import (
    fetch_guild_text_channels, fetch_guild_voice_channels, fetch_guild_categories, fetch_guild_roles,
)
from dashboard.backend.admin_routes import admin_router
from dashboard.backend.application_routes import application_router
from dashboard.backend.server_extra_routes import server_extra_router
from bot.database.db import init_db, get_session
from bot.utils.db_helpers import (
    upsert_dashboard_user,
    get_bot_guild_ids,
    save_guild_settings_from_dashboard,
    get_or_create_guild_settings,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("dashboard.main")

app = FastAPI(title="Bot Dashboard")
app.add_middleware(SessionMiddleware, secret_key=cfg.SESSION_SECRET, same_site="lax")
app.mount("/static", StaticFiles(directory="dashboard/backend/static"), name="static")
from dashboard.backend.template_context import global_template_context
templates = Jinja2Templates(directory="dashboard/backend/templates", context_processors=[global_template_context])
app.include_router(admin_router)
app.include_router(application_router)
app.include_router(server_extra_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Loggt den VOLLEN Traceback (landet in den Render-Logs) UND zeigt eine
    # freundliche Seite statt der nackten "Internal Server Error" -- so
    # bleibt die Ursache immer im Log nachvollziehbar, egal was passiert.
    log.exception("Unbehandelter Fehler bei %s %s", request.method, request.url.path)
    return PlainTextResponse(
        "Es ist ein unerwarteter Fehler aufgetreten. Das wurde geloggt — "
        "bitte kurz warten und nochmal versuchen, oder den Betreiber kontaktieren.",
        status_code=500,
    )


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
    return templates.TemplateResponse(request, "landing.html", {"user": None, "messages": []})


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

    # Falls der Login vom Bewerbungsformular ausgelöst wurde, dorthin zurückleiten
    # statt immer zur Server-Übersicht.
    redirect_target = request.session.pop("post_login_redirect", None)
    return RedirectResponse(redirect_target or "/servers")


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
    try:
        user_guilds = await discord_oauth.fetch_user_guilds(access_token)
    except httpx.HTTPStatusError:
        return templates.TemplateResponse(request, "guilds.html", {
            "user": user,
            "messages": [{"type": "error", "text": "Discord ist gerade überlastet — bitte in ein paar "
                                                     "Sekunden nochmal versuchen."}],
            "manageable_guilds": [], "invite_url": "",
        })
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
    """Prüft Zugriff und gibt bei Erfolg (None, guild_dict) zurück, bei Ablehnung
    (redirect_response, None). So muss der Aufrufer NICHT selbst nochmal bei
    Discord nachfragen (der /users/@me/guilds-Endpunkt ist scharf rate-limitiert
    -- ein doppelter Aufruf pro Seitenaufruf war ein echtes Risiko)."""
    user = _current_user(request)
    if not user:
        return RedirectResponse("/"), None

    bot_guild_ids = await get_bot_guild_ids()
    if guild_id not in bot_guild_ids:
        return RedirectResponse("/servers?error=bot_not_present"), None

    access_token = request.session.get("access_token", "")
    try:
        user_guilds = await discord_oauth.fetch_user_guilds(access_token)
    except httpx.HTTPStatusError:
        return RedirectResponse("/servers?error=rate_limited"), None
    match = next((g for g in user_guilds if int(g["id"]) == guild_id), None)
    if not match or not discord_oauth.can_manage_guild(match["permissions"]):
        return RedirectResponse("/servers?error=no_access"), None

    return None, match


@app.get("/dashboard/{guild_id}", response_class=HTMLResponse)
async def guild_settings_page(request: Request, guild_id: int):
    denied, guild = await _require_guild_access(request, guild_id)
    if denied:
        return denied

    user = _current_user(request)
    async with get_session() as session:
        settings = await get_or_create_guild_settings(session, guild_id)

    text_channels = await fetch_guild_text_channels(guild_id)
    voice_channels = await fetch_guild_voice_channels(guild_id)
    categories = await fetch_guild_categories(guild_id)
    roles = await fetch_guild_roles(guild_id)

    return templates.TemplateResponse(request, "settings.html", {
        "user": user, "messages": [],
        "guild": {"id": guild_id, "name": guild["name"]},
        "settings": settings,
        "text_channels": text_channels,
        "voice_channels": voice_channels,
        "categories": categories,
        "roles": roles,
    })


@app.post("/dashboard/{guild_id}/settings")
async def save_guild_settings(
    request: Request, guild_id: int,
    language: str = Form("de"),
    mod_log_channel_id: int = Form(0),
    punishment_log_channel_id: int = Form(0),
    announcement_channel_id: int = Form(0),
    ticket_category_id: int = Form(0),
    waiting_room_voice_channel_id: int = Form(0),
    waiting_room_notify_channel_id: int = Form(0),
    autorole_id: int = Form(0),
    anti_nuke_enabled: str = Form(""),
    anti_spam_enabled: str = Form(""),
    music_bound_voice_channel_id: int = Form(0),
):
    denied, _guild = await _require_guild_access(request, guild_id)
    if denied:
        return denied

    await save_guild_settings_from_dashboard(
        guild_id, language, mod_log_channel_id, punishment_log_channel_id, announcement_channel_id,
        ticket_category_id, waiting_room_voice_channel_id, waiting_room_notify_channel_id,
        autorole_id, anti_nuke_enabled == "on", anti_spam_enabled == "on",
        music_bound_voice_channel_id,
    )
    return RedirectResponse(f"/dashboard/{guild_id}?saved=1", status_code=303)
