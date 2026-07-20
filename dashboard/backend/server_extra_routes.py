"""
Zusätzliche Server-Dashboard-Seiten (über die Basis-Einstellungen hinaus):

- /dashboard/{id}/team              -- Team-Ränge + Mitgliederliste (Ansicht)
- /dashboard/{id}/levelrollen         -- Level-Rang-Rollen verwalten
- /dashboard/{id}/vertrauensliste      -- Anti-Nuke-Whitelist verwalten
- /dashboard/{id}/gewinnspiele           -- laufende/beendete Gewinnspiele (Ansicht)
- /dashboard/{id}/strafen                 -- aktives Strafverzeichnis (Ansicht)
- /dashboard/{id}/leaderboard               -- XP-Bestenliste (Ansicht)
"""
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from bot.utils.db_helpers import (
    get_team_ranks,
    get_all_team_members,
    get_level_role_rewards,
    add_level_role_reward,
    remove_level_role_reward,
    get_trusted_users,
    add_trusted_user,
    remove_trusted_user,
    get_giveaways_for_guild,
    get_guild_punishments,
    get_leaderboard,
    log_punishment,
    get_or_create_guild_settings,
    get_tickets_for_guild,
)
from bot.database.db import get_session
from dashboard.backend.bot_api import (
    fetch_guild_roles, fetch_guild_text_channels, kick_member, ban_member, send_channel_message,
)
from dashboard.backend.template_context import global_template_context

server_extra_router = APIRouter()
templates = Jinja2Templates(directory="dashboard/backend/templates", context_processors=[global_template_context])


def _current_user(request: Request):
    return request.session.get("user")


async def _require_guild_admin(request: Request, guild_id: int):
    """Lokaler Import, um einen Ringimport mit main.py zu vermeiden (siehe
    application_routes.py, gleiches Muster)."""
    from dashboard.backend.main import _require_guild_access
    return await _require_guild_access(request, guild_id)


@server_extra_router.get("/dashboard/{guild_id}/team", response_class=HTMLResponse)
async def team_page(request: Request, guild_id: int):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    ranks = await get_team_ranks(guild_id)
    members = await get_all_team_members(guild_id)
    ranks_by_id = {r.id: r for r in ranks}
    return templates.TemplateResponse(request, "dash_team.html", {
        "user": _current_user(request), "messages": [],
        "guild": {"id": guild_id, "name": guild["name"]},
        "ranks": ranks, "members": members, "ranks_by_id": ranks_by_id,
    })


@server_extra_router.get("/dashboard/{guild_id}/levelrollen", response_class=HTMLResponse)
async def level_roles_page(request: Request, guild_id: int):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    rewards = await get_level_role_rewards(guild_id)
    roles = await fetch_guild_roles(guild_id)
    return templates.TemplateResponse(request, "dash_levelrollen.html", {
        "user": _current_user(request), "messages": [],
        "guild": {"id": guild_id, "name": guild["name"]},
        "rewards": rewards, "roles": roles,
    })


@server_extra_router.post("/dashboard/{guild_id}/levelrollen")
async def level_roles_add(request: Request, guild_id: int, level: int = Form(...), role_id: int = Form(...)):
    denied, _guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    if role_id:
        await add_level_role_reward(guild_id, level, role_id)
    return RedirectResponse(f"/dashboard/{guild_id}/levelrollen", status_code=303)


@server_extra_router.post("/dashboard/{guild_id}/levelrollen/{reward_id}/loeschen")
async def level_roles_remove(request: Request, guild_id: int, reward_id: int):
    denied, _guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    await remove_level_role_reward(reward_id)
    return RedirectResponse(f"/dashboard/{guild_id}/levelrollen", status_code=303)


@server_extra_router.get("/dashboard/{guild_id}/vertrauensliste", response_class=HTMLResponse)
async def trusted_users_page(request: Request, guild_id: int):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    trusted = await get_trusted_users(guild_id)
    return templates.TemplateResponse(request, "dash_vertrauensliste.html", {
        "user": _current_user(request), "messages": [],
        "guild": {"id": guild_id, "name": guild["name"]},
        "trusted": trusted,
    })


@server_extra_router.post("/dashboard/{guild_id}/vertrauensliste")
async def trusted_users_add(request: Request, guild_id: int, discord_id: int = Form(...)):
    denied, _guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    user = _current_user(request)
    await add_trusted_user(guild_id, discord_id, int(user["discord_id"]))
    return RedirectResponse(f"/dashboard/{guild_id}/vertrauensliste", status_code=303)


@server_extra_router.post("/dashboard/{guild_id}/vertrauensliste/{discord_id}/entfernen")
async def trusted_users_remove(request: Request, guild_id: int, discord_id: int):
    denied, _guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    await remove_trusted_user(guild_id, discord_id)
    return RedirectResponse(f"/dashboard/{guild_id}/vertrauensliste", status_code=303)


@server_extra_router.get("/dashboard/{guild_id}/gewinnspiele", response_class=HTMLResponse)
async def giveaways_page(request: Request, guild_id: int):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    giveaways = await get_giveaways_for_guild(guild_id)
    return templates.TemplateResponse(request, "dash_gewinnspiele.html", {
        "user": _current_user(request), "messages": [],
        "guild": {"id": guild_id, "name": guild["name"]},
        "giveaways": giveaways,
    })


@server_extra_router.get("/dashboard/{guild_id}/strafen", response_class=HTMLResponse)
async def punishments_page(request: Request, guild_id: int):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    punishments = await get_guild_punishments(guild_id)
    return templates.TemplateResponse(request, "dash_strafen.html", {
        "user": _current_user(request), "messages": [],
        "guild": {"id": guild_id, "name": guild["name"]},
        "punishments": punishments,
    })


@server_extra_router.get("/dashboard/{guild_id}/leaderboard", response_class=HTMLResponse)
async def leaderboard_page(request: Request, guild_id: int):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    top = await get_leaderboard(guild_id, limit=25)
    return templates.TemplateResponse(request, "dash_leaderboard.html", {
        "user": _current_user(request), "messages": [],
        "guild": {"id": guild_id, "name": guild["name"]},
        "top": top,
    })


@server_extra_router.get("/dashboard/{guild_id}/moderation", response_class=HTMLResponse)
async def moderation_page(request: Request, guild_id: int):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    return templates.TemplateResponse(request, "dash_moderation.html", {
        "user": _current_user(request), "messages": [],
        "guild": {"id": guild_id, "name": guild["name"]},
    })


@server_extra_router.post("/dashboard/{guild_id}/moderation/kick")
async def moderation_kick(request: Request, guild_id: int, user_id: int = Form(...),
                           reason: str = Form("Kein Grund angegeben")):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    # Hinweis: dieser Weg umgeht die Rollen-Hierarchie-Prüfung der Discord-Befehle
    # (/kick) -- der Zugriff aufs Dashboard selbst ist aber schon durch die
    # Discord-"Manage Server"-Berechtigung für GENAU diesen Server abgesichert.
    ok = await kick_member(guild_id, user_id, reason)
    return templates.TemplateResponse(request, "dash_moderation.html", {
        "user": _current_user(request),
        "guild": {"id": guild_id, "name": guild["name"]},
        "messages": [{"type": "success" if ok else "error",
                      "text": "User gekickt." if ok else "Kick fehlgeschlagen (Berechtigung des Bots prüfen)."}],
    })


@server_extra_router.post("/dashboard/{guild_id}/moderation/ban")
async def moderation_ban(request: Request, guild_id: int, user_id: int = Form(...),
                          reason: str = Form("Kein Grund angegeben")):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    ok = await ban_member(guild_id, user_id, reason)
    return templates.TemplateResponse(request, "dash_moderation.html", {
        "user": _current_user(request),
        "guild": {"id": guild_id, "name": guild["name"]},
        "messages": [{"type": "success" if ok else "error",
                      "text": "User gebannt." if ok else "Bann fehlgeschlagen (Berechtigung des Bots prüfen)."}],
    })


@server_extra_router.post("/dashboard/{guild_id}/moderation/warn")
async def moderation_warn(request: Request, guild_id: int, user_id: int = Form(...),
                           reason: str = Form("Kein Grund angegeben")):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    user = _current_user(request)
    await log_punishment(guild_id, user_id, int(user["discord_id"]), "warn", reason)
    return templates.TemplateResponse(request, "dash_moderation.html", {
        "user": user,
        "guild": {"id": guild_id, "name": guild["name"]},
        "messages": [{"type": "success", "text": "Verwarnung gespeichert."}],
    })


@server_extra_router.get("/dashboard/{guild_id}/ankuendigung", response_class=HTMLResponse)
async def server_announcement_page(request: Request, guild_id: int):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    channels = await fetch_guild_text_channels(guild_id)
    return templates.TemplateResponse(request, "dash_ankuendigung.html", {
        "user": _current_user(request), "messages": [],
        "guild": {"id": guild_id, "name": guild["name"]},
        "channels": channels,
    })


@server_extra_router.post("/dashboard/{guild_id}/ankuendigung")
async def server_announcement_send(request: Request, guild_id: int, channel_id: int = Form(...),
                                    message: str = Form(...)):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    ok = await send_channel_message(channel_id, message)
    channels = await fetch_guild_text_channels(guild_id)
    return templates.TemplateResponse(request, "dash_ankuendigung.html", {
        "user": _current_user(request), "channels": channels,
        "guild": {"id": guild_id, "name": guild["name"]},
        "messages": [{"type": "success" if ok else "error",
                      "text": "Gesendet." if ok else "Senden fehlgeschlagen."}],
    })


@server_extra_router.get("/dashboard/{guild_id}/tickets", response_class=HTMLResponse)
async def tickets_page(request: Request, guild_id: int):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    tickets = await get_tickets_for_guild(guild_id)
    return templates.TemplateResponse(request, "dash_tickets.html", {
        "user": _current_user(request), "messages": [],
        "guild": {"id": guild_id, "name": guild["name"]},
        "tickets": tickets,
    })
