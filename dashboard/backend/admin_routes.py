"""
Admin-Panel-Routen. Eigener, komplett getrennter Login (Passwort statt
Discord-OAuth) -- siehe admin_auth.py. Wird in main.py per
app.include_router(admin_router) eingebunden.

Berechtigungs-Schlüssel (permission_key), die vergeben werden können:
  servers.view      -- Serverliste + Einladungslinks sehen
  broadcast.send     -- globale Ankündigungen senden
  bot.control          -- Wartungsmodus umschalten
  users.view            -- Dashboard-User-Liste sehen
  permissions.manage     -- anderen Admins Rechte geben/entziehen (nur Superadmin ohnehin immer erlaubt)
"""
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from dashboard.backend.admin_auth import hash_password, verify_password
from dashboard.backend.bot_api import send_channel_message, create_guild_invite
from bot.utils.db_helpers import (
    get_admin_user_by_username,
    create_admin_user,
    count_admin_users,
    update_admin_last_login,
    list_admin_users,
    get_admin_permissions,
    grant_admin_permission,
    revoke_admin_permission,
    get_bot_control_state,
    set_maintenance_mode,
    log_global_announcement,
    get_all_bot_guilds,
    get_or_create_guild_settings,
)
from bot.database.db import get_session
from dashboard.backend.config import dashboard_config as cfg

admin_router = APIRouter()
templates = Jinja2Templates(directory="dashboard/backend/templates")

ALL_PERMISSIONS = ["servers.view", "broadcast.send", "bot.control", "users.view", "permissions.manage"]


def _current_admin(request: Request) -> dict | None:
    return request.session.get("admin_user")


async def _require_admin(request: Request):
    """Gibt None zurück, wenn eingeloggt, sonst eine Redirect-Response."""
    if not _current_admin(request):
        return RedirectResponse("/admin/login")
    return None


async def _require_permission(request: Request, permission_key: str):
    admin = _current_admin(request)
    if not admin:
        return RedirectResponse("/admin/login")
    if admin.get("is_superadmin"):
        return None
    perms = await get_admin_permissions(admin["id"])
    if permission_key not in perms:
        return RedirectResponse("/admin?error=no_permission")
    return None


@admin_router.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    if _current_admin(request):
        return RedirectResponse("/admin")
    # Bootstrap: existiert noch kein einziger Admin-Account, aber Zugangsdaten
    # sind in der .env hinterlegt -> jetzt anlegen (Passwort sofort gehasht).
    if await count_admin_users() == 0 and cfg.ADMIN_BOOTSTRAP_USERNAME and cfg.ADMIN_BOOTSTRAP_PASSWORD:
        await create_admin_user(
            cfg.ADMIN_BOOTSTRAP_USERNAME, hash_password(cfg.ADMIN_BOOTSTRAP_PASSWORD), is_superadmin=True,
        )
    return templates.TemplateResponse(request, "admin_login.html", {"user": None, "messages": []})


@admin_router.post("/admin/login")
async def admin_login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    admin = await get_admin_user_by_username(username)
    if not admin or not verify_password(password, admin.password_hash):
        return templates.TemplateResponse(request, "admin_login.html", {
            "user": None,
            "messages": [{"type": "error", "text": "Benutzername oder Passwort falsch."}],
        })

    request.session["admin_user"] = {
        "id": admin.id, "username": admin.username, "is_superadmin": admin.is_superadmin,
    }
    await update_admin_last_login(admin.id)
    return RedirectResponse("/admin", status_code=303)


@admin_router.get("/admin/logout")
async def admin_logout(request: Request):
    request.session.pop("admin_user", None)
    return RedirectResponse("/admin/login")


@admin_router.get("/admin", response_class=HTMLResponse)
async def admin_home(request: Request):
    denied = await _require_admin(request)
    if denied:
        return denied

    admin = _current_admin(request)
    guilds = await get_all_bot_guilds()
    state = await get_bot_control_state()

    return templates.TemplateResponse(request, "admin_home.html", {
        "user": None, "messages": [], "admin": admin,
        "guild_count": len(guilds),
        "total_members": sum(g.member_count for g in guilds),
        "maintenance_mode": state.maintenance_mode,
    })


@admin_router.get("/admin/servers", response_class=HTMLResponse)
async def admin_servers(request: Request):
    denied = await _require_permission(request, "servers.view")
    if denied:
        return denied
    admin = _current_admin(request)
    guilds = await get_all_bot_guilds()
    return templates.TemplateResponse(request, "admin_servers.html", {
        "user": None, "messages": [], "admin": admin, "guilds": guilds,
    })


@admin_router.post("/admin/servers/{guild_id}/invite")
async def admin_generate_invite(request: Request, guild_id: int):
    denied = await _require_permission(request, "servers.view")
    if denied:
        return denied
    admin = _current_admin(request)
    guilds = await get_all_bot_guilds()
    invite_url = await create_guild_invite(guild_id)
    return templates.TemplateResponse(request, "admin_servers.html", {
        "user": None, "admin": admin, "guilds": guilds,
        "messages": [{"type": "success" if invite_url else "error",
                      "text": f"Einladungslink: {invite_url}" if invite_url
                      else "Konnte keinen Einladungslink erzeugen (fehlende Berechtigung des Bots?)."}],
    })


@admin_router.get("/admin/broadcast", response_class=HTMLResponse)
async def admin_broadcast_page(request: Request):
    denied = await _require_permission(request, "broadcast.send")
    if denied:
        return denied
    admin = _current_admin(request)
    guilds = await get_all_bot_guilds()
    return templates.TemplateResponse(request, "admin_broadcast.html", {
        "user": None, "messages": [], "admin": admin, "guild_count": len(guilds),
    })


@admin_router.post("/admin/broadcast")
async def admin_broadcast_send(request: Request, message: str = Form(...)):
    denied = await _require_permission(request, "broadcast.send")
    if denied:
        return denied
    admin = _current_admin(request)

    guilds = await get_all_bot_guilds()
    sent_count = 0
    for guild in guilds:
        async with get_session() as session:
            settings = await get_or_create_guild_settings(session, guild.guild_id)
            channel_id = settings.announcement_channel_id
        if channel_id:
            ok = await send_channel_message(channel_id, message)
            if ok:
                sent_count += 1

    await log_global_announcement(message, sent_count, admin["id"])

    return templates.TemplateResponse(request, "admin_broadcast.html", {
        "user": None, "admin": admin, "guild_count": len(guilds),
        "messages": [{"type": "success", "text": f"An {sent_count} von {len(guilds)} Server(n) gesendet "
                                                   f"(nur Server mit eingerichtetem Ankündigungskanal)."}],
    })


@admin_router.get("/admin/bot-control", response_class=HTMLResponse)
async def admin_bot_control_page(request: Request):
    denied = await _require_permission(request, "bot.control")
    if denied:
        return denied
    admin = _current_admin(request)
    state = await get_bot_control_state()
    return templates.TemplateResponse(request, "admin_bot_control.html", {
        "user": None, "messages": [], "admin": admin, "state": state,
    })


@admin_router.post("/admin/bot-control")
async def admin_bot_control_submit(request: Request, enable: str = Form(""), reason: str = Form("")):
    denied = await _require_permission(request, "bot.control")
    if denied:
        return denied
    admin = _current_admin(request)
    await set_maintenance_mode(enable == "on", reason, admin["id"])
    state = await get_bot_control_state()
    return templates.TemplateResponse(request, "admin_bot_control.html", {
        "user": None, "admin": admin, "state": state,
        "messages": [{"type": "success", "text": "Gespeichert. Der Bot übernimmt die Änderung innerhalb von "
                                                   "ca. 20 Sekunden (er fragt periodisch selbst nach)."}],
    })


@admin_router.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request):
    denied = await _require_permission(request, "users.view")
    if denied:
        return denied
    admin = _current_admin(request)

    from bot.database.models import DashboardUser
    from sqlalchemy import select
    async with get_session() as session:
        result = await session.execute(select(DashboardUser).order_by(DashboardUser.last_login_at.desc()))
        dashboard_users = list(result.scalars().all())

    return templates.TemplateResponse(request, "admin_users.html", {
        "user": None, "messages": [], "admin": admin, "dashboard_users": dashboard_users,
    })


@admin_router.get("/admin/permissions", response_class=HTMLResponse)
async def admin_permissions_page(request: Request):
    admin = _current_admin(request)
    if not admin:
        return RedirectResponse("/admin/login")
    if not admin.get("is_superadmin"):
        return RedirectResponse("/admin?error=no_permission")

    admins = await list_admin_users()
    admins_with_perms = []
    for a in admins:
        perms = await get_admin_permissions(a.id) if not a.is_superadmin else set(ALL_PERMISSIONS)
        admins_with_perms.append({"user": a, "permissions": perms})

    return templates.TemplateResponse(request, "admin_permissions.html", {
        "user": None, "messages": [], "admin": admin,
        "admins_with_perms": admins_with_perms, "all_permissions": ALL_PERMISSIONS,
    })


@admin_router.post("/admin/permissions/{admin_id}/toggle")
async def admin_permissions_toggle(request: Request, admin_id: int, permission_key: str = Form(...),
                                    action: str = Form(...)):
    admin = _current_admin(request)
    if not admin or not admin.get("is_superadmin"):
        return RedirectResponse("/admin/login")

    if action == "grant":
        await grant_admin_permission(admin_id, permission_key, admin["id"])
    else:
        await revoke_admin_permission(admin_id, permission_key)

    return RedirectResponse("/admin/permissions", status_code=303)


@admin_router.post("/admin/create-admin")
async def admin_create_new(request: Request, username: str = Form(...), password: str = Form(...)):
    admin = _current_admin(request)
    if not admin or not admin.get("is_superadmin"):
        return RedirectResponse("/admin/login")

    existing = await get_admin_user_by_username(username)
    if existing:
        return RedirectResponse("/admin/permissions?error=exists", status_code=303)

    await create_admin_user(username, hash_password(password), is_superadmin=False)
    return RedirectResponse("/admin/permissions", status_code=303)


@admin_router.get("/impressum", response_class=HTMLResponse)
async def impressum(request: Request):
    return templates.TemplateResponse(request, "impressum.html", {"user": None, "messages": []})
