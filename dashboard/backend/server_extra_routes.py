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
    add_team_rank,
    remove_team_rank,
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
    add_anti_exemption,
    remove_anti_exemption,
    get_anti_exemptions,
    get_ticket_categories,
    create_ticket_category,
    delete_ticket_category,
    count_open_tickets_by_category,
    get_welcome_config,
    set_welcome_settings,
)
from dashboard.backend.bot_api import (
    fetch_guild_roles, fetch_guild_text_channels, kick_member, ban_member, send_channel_message,
    fetch_guild_members, add_role_to_member, set_channel_slowmode, set_channel_lock, set_member_nickname,
    fetch_guild_categories, send_ticket_panel,
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
    roles = await fetch_guild_roles(guild_id)
    return templates.TemplateResponse(request, "dash_team.html", {
        "user": _current_user(request), "messages": [],
        "guild": {"id": guild_id, "name": guild["name"]},
        "ranks": ranks, "members": members, "ranks_by_id": ranks_by_id, "roles": roles,
    })


@server_extra_router.post("/dashboard/{guild_id}/team/raenge")
async def team_rank_add(request: Request, guild_id: int, role_id: int = Form(...)):
    denied, _guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    if role_id:
        await add_team_rank(guild_id, role_id)
    return RedirectResponse(f"/dashboard/{guild_id}/team", status_code=303)


@server_extra_router.post("/dashboard/{guild_id}/team/raenge/{rank_id}/loeschen")
async def team_rank_remove(request: Request, guild_id: int, rank_id: int):
    denied, _guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    await remove_team_rank(rank_id)
    return RedirectResponse(f"/dashboard/{guild_id}/team", status_code=303)


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
    channels = await fetch_guild_text_channels(guild_id)
    roles = await fetch_guild_roles(guild_id)
    return templates.TemplateResponse(request, "dash_moderation.html", {
        "user": _current_user(request), "messages": [],
        "guild": {"id": guild_id, "name": guild["name"]},
        "channels": channels, "roles": roles,
    })


async def _moderation_context(guild_id: int) -> dict:
    """Kanäle + Rollen fürs Moderation-Formular -- an einer Stelle, damit
    nicht jede der 8 moderation_*-Routen das einzeln wiederholen muss."""
    return {
        "channels": await fetch_guild_text_channels(guild_id),
        "roles": await fetch_guild_roles(guild_id),
    }


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
        **(await _moderation_context(guild_id)),
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
        **(await _moderation_context(guild_id)),
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
        **(await _moderation_context(guild_id)),
        "messages": [{"type": "success", "text": "Verwarnung gespeichert."}],
    })


@server_extra_router.post("/dashboard/{guild_id}/moderation/autorole-all")
async def moderation_autorole_all(request: Request, guild_id: int, role_id: int = Form(...)):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied

    members = await fetch_guild_members(guild_id)
    given, already_had, failed = 0, 0, 0
    for member in members:
        if member.get("user", {}).get("bot"):
            continue
        if str(role_id) in member.get("roles", []):
            already_had += 1
            continue
        ok = await add_role_to_member(guild_id, int(member["user"]["id"]), role_id, "Dashboard: Autorole an alle")
        if ok:
            given += 1
        else:
            failed += 1

    text = f"{given} Mitgliedern die Rolle gegeben. {already_had} hatten sie schon."
    if failed:
        text += f" {failed} fehlgeschlagen."
    return templates.TemplateResponse(request, "dash_moderation.html", {
        "user": _current_user(request),
        "guild": {"id": guild_id, "name": guild["name"]},
        **(await _moderation_context(guild_id)),
        "messages": [{"type": "success", "text": text}],
    })


@server_extra_router.post("/dashboard/{guild_id}/moderation/slowmode")
async def moderation_slowmode(request: Request, guild_id: int, channel_id: int = Form(...),
                               seconds: int = Form(...)):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    if seconds < 0 or seconds > 21600:
        text, msg_type = "Wert muss zwischen 0 und 21600 liegen.", "error"
    else:
        ok = await set_channel_slowmode(channel_id, seconds)
        text = "Slowmode gesetzt." if ok else "Fehlgeschlagen (Berechtigung des Bots prüfen)."
        msg_type = "success" if ok else "error"
    return templates.TemplateResponse(request, "dash_moderation.html", {
        "user": _current_user(request),
        "guild": {"id": guild_id, "name": guild["name"]},
        **(await _moderation_context(guild_id)),
        "messages": [{"type": msg_type, "text": text}],
    })


@server_extra_router.post("/dashboard/{guild_id}/moderation/lock")
async def moderation_lock(request: Request, guild_id: int, channel_id: int = Form(...)):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    ok = await set_channel_lock(guild_id, channel_id, locked=True)
    return templates.TemplateResponse(request, "dash_moderation.html", {
        "user": _current_user(request),
        "guild": {"id": guild_id, "name": guild["name"]},
        **(await _moderation_context(guild_id)),
        "messages": [{"type": "success" if ok else "error",
                      "text": "Kanal gesperrt." if ok else "Fehlgeschlagen (Berechtigung des Bots prüfen)."}],
    })


@server_extra_router.post("/dashboard/{guild_id}/moderation/unlock")
async def moderation_unlock(request: Request, guild_id: int, channel_id: int = Form(...)):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    ok = await set_channel_lock(guild_id, channel_id, locked=False)
    return templates.TemplateResponse(request, "dash_moderation.html", {
        "user": _current_user(request),
        "guild": {"id": guild_id, "name": guild["name"]},
        **(await _moderation_context(guild_id)),
        "messages": [{"type": "success" if ok else "error",
                      "text": "Kanal entsperrt." if ok else "Fehlgeschlagen (Berechtigung des Bots prüfen)."}],
    })


@server_extra_router.post("/dashboard/{guild_id}/moderation/nickname")
async def moderation_nickname(request: Request, guild_id: int, user_id: int = Form(...),
                               nickname: str = Form("")):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    ok = await set_member_nickname(guild_id, user_id, nickname)
    return templates.TemplateResponse(request, "dash_moderation.html", {
        "user": _current_user(request),
        "guild": {"id": guild_id, "name": guild["name"]},
        **(await _moderation_context(guild_id)),
        "messages": [{"type": "success" if ok else "error",
                      "text": "Spitzname geändert." if ok else "Fehlgeschlagen (Berechtigung des Bots prüfen)."}],
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


async def _exemptions_page(request: Request, guild_id: int, feature: str, template: str, label: str):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    entries = await get_anti_exemptions(guild_id, feature)
    return templates.TemplateResponse(request, template, {
        "user": _current_user(request), "messages": [],
        "guild": {"id": guild_id, "name": guild["name"]},
        "entries": entries, "feature_label": label,
    })


async def _exemptions_add(request: Request, guild_id: int, feature: str, target_type: str,
                           target_id: int, redirect_path: str):
    denied, _guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    user = _current_user(request)
    await add_anti_exemption(guild_id, feature, target_type, target_id, int(user["discord_id"]))
    return RedirectResponse(redirect_path, status_code=303)


async def _exemptions_remove(request: Request, guild_id: int, feature: str, target_type: str,
                              target_id: int, redirect_path: str):
    denied, _guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    await remove_anti_exemption(guild_id, feature, target_type, target_id)
    return RedirectResponse(redirect_path, status_code=303)


@server_extra_router.get("/dashboard/{guild_id}/antihack-ausnahmen", response_class=HTMLResponse)
async def antihack_exemptions_page(request: Request, guild_id: int):
    return await _exemptions_page(request, guild_id, "antihack", "dash_exemptions.html", "Anti-Hack")


@server_extra_router.post("/dashboard/{guild_id}/antihack-ausnahmen")
async def antihack_exemptions_add(request: Request, guild_id: int, target_type: str = Form(...),
                                   target_id: int = Form(...)):
    return await _exemptions_add(request, guild_id, "antihack", target_type, target_id,
                                  f"/dashboard/{guild_id}/antihack-ausnahmen")


@server_extra_router.post("/dashboard/{guild_id}/antihack-ausnahmen/{target_type}/{target_id}/entfernen")
async def antihack_exemptions_remove(request: Request, guild_id: int, target_type: str, target_id: int):
    return await _exemptions_remove(request, guild_id, "antihack", target_type, target_id,
                                     f"/dashboard/{guild_id}/antihack-ausnahmen")


@server_extra_router.get("/dashboard/{guild_id}/antiwerbung-ausnahmen", response_class=HTMLResponse)
async def antiwerbung_exemptions_page(request: Request, guild_id: int):
    return await _exemptions_page(request, guild_id, "antiwerbung", "dash_exemptions.html", "Anti-Werbung")


@server_extra_router.post("/dashboard/{guild_id}/antiwerbung-ausnahmen")
async def antiwerbung_exemptions_add(request: Request, guild_id: int, target_type: str = Form(...),
                                      target_id: int = Form(...)):
    return await _exemptions_add(request, guild_id, "antiwerbung", target_type, target_id,
                                  f"/dashboard/{guild_id}/antiwerbung-ausnahmen")


@server_extra_router.post("/dashboard/{guild_id}/antiwerbung-ausnahmen/{target_type}/{target_id}/entfernen")
async def antiwerbung_exemptions_remove(request: Request, guild_id: int, target_type: str, target_id: int):
    return await _exemptions_remove(request, guild_id, "antiwerbung", target_type, target_id,
                                     f"/dashboard/{guild_id}/antiwerbung-ausnahmen")

# ---------- Ticket-Setups (Dashboard) ----------

@server_extra_router.get("/dashboard/{guild_id}/tickets/kategorien", response_class=HTMLResponse)
async def ticket_categories_page(request: Request, guild_id: int):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    cats = await get_ticket_categories(guild_id)
    entries = []
    for c in cats:
        open_count = await count_open_tickets_by_category(c.id) if c.max_concurrent else 0
        entries.append({"category": c, "open_count": open_count})
    discord_categories = await fetch_guild_categories(guild_id)
    roles = await fetch_guild_roles(guild_id)
    return templates.TemplateResponse(request, "dash_ticket_kategorien.html", {
        "user": _current_user(request), "messages": [],
        "guild": {"id": guild_id, "name": guild["name"]},
        "categories": entries, "discord_categories": discord_categories, "roles": roles,
    })

@server_extra_router.post("/dashboard/{guild_id}/tickets/kategorien")
async def ticket_categories_add(
    request: Request, guild_id: int, name: str = Form(...), emoji: str = Form("🎫"),
    description: str = Form(""), channel_category_id: int = Form(0),
    max_concurrent: int = Form(0), ping_role_id: int = Form(0),
):
    denied, _guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    await create_ticket_category(
        guild_id, name=name, emoji=emoji or "🎫", description=description,
        channel_category_id=channel_category_id, max_concurrent=max(0, max_concurrent),
        ping_role_id=ping_role_id,
    )
    return RedirectResponse(f"/dashboard/{guild_id}/tickets/kategorien", status_code=303)

@server_extra_router.post("/dashboard/{guild_id}/tickets/kategorien/{category_id}/loeschen")
async def ticket_categories_remove(request: Request, guild_id: int, category_id: int):
    denied, _guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    await delete_ticket_category(category_id)
    return RedirectResponse(f"/dashboard/{guild_id}/tickets/kategorien", status_code=303)

@server_extra_router.get("/dashboard/{guild_id}/tickets/panel-senden", response_class=HTMLResponse)
async def ticket_panel_send_page(request: Request, guild_id: int):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    categories = await get_ticket_categories(guild_id)
    channels = await fetch_guild_text_channels(guild_id)
    return templates.TemplateResponse(request, "dash_ticket_panel_senden.html", {
        "user": _current_user(request), "messages": [],
        "guild": {"id": guild_id, "name": guild["name"]},
        "categories": categories, "channels": channels,
        "designs": ["standard", "minimal", "premium", "dark"],
    })

@server_extra_router.post("/dashboard/{guild_id}/tickets/panel-senden")
async def ticket_panel_send_action(request: Request, guild_id: int, channel_id: int = Form(...),
                                    design: str = Form("standard")):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    ok = await send_ticket_panel(guild_id, channel_id, design)
    categories = await get_ticket_categories(guild_id)
    channels = await fetch_guild_text_channels(guild_id)
    return templates.TemplateResponse(request, "dash_ticket_panel_senden.html", {
        "user": _current_user(request),
        "guild": {"id": guild_id, "name": guild["name"]},
        "categories": categories, "channels": channels,
        "designs": ["standard", "minimal", "premium", "dark"],
        "messages": [{"type": "success" if ok else "error",
                      "text": "Panel gesendet." if ok else "Senden fehlgeschlagen (Berechtigung des Bots prüfen)."}],
    })

# ---------- Willkommen/Abschied (Dashboard) ----------

@server_extra_router.get("/dashboard/{guild_id}/willkommen", response_class=HTMLResponse)
async def welcome_page(request: Request, guild_id: int):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    cfg_row = await get_welcome_config(guild_id)
    channels = await fetch_guild_text_channels(guild_id)
    return templates.TemplateResponse(request, "dash_willkommen.html", {
        "user": _current_user(request), "messages": [],
        "guild": {"id": guild_id, "name": guild["name"]},
        "config": cfg_row, "channels": channels,
    })

@server_extra_router.post("/dashboard/{guild_id}/willkommen")
async def welcome_save(
    request: Request, guild_id: int,
    welcome_enabled: str = Form(""), welcome_channel_id: int = Form(0), welcome_message: str = Form(""),
    goodbye_enabled: str = Form(""), goodbye_channel_id: int = Form(0), goodbye_message: str = Form(""),
):
    denied, _guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    await set_welcome_settings(
        guild_id,
        welcome_enabled=welcome_enabled == "on", welcome_channel_id=welcome_channel_id,
        welcome_message=welcome_message,
        goodbye_enabled=goodbye_enabled == "on", goodbye_channel_id=goodbye_channel_id,
        goodbye_message=goodbye_message,
    )
    return RedirectResponse(f"/dashboard/{guild_id}/willkommen?saved=1", status_code=303)
