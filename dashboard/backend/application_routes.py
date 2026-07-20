"""
Bewerbungssystem-Routen.

- GET  /bewerbung/{guild_id}                        -- öffentliches Formular (Login über Discord nötig)
- POST /bewerbung/{guild_id}                          -- Bewerbung abschicken
- GET  /dashboard/{guild_id}/bewerbung/einstellungen   -- Fragen konfigurieren (SERVER_ADMIN)
- GET  /dashboard/{guild_id}/bewerbungen                -- eingegangene Bewerbungen (SERVER_ADMIN)
- POST /dashboard/{guild_id}/bewerbungen/{id}/status     -- annehmen/ablehnen (SERVER_ADMIN)
"""
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from bot.utils.db_helpers import (
    get_application_config,
    set_application_config,
    get_application_questions,
    add_application_question,
    remove_application_question,
    has_pending_application,
    create_application,
    get_applications_for_guild,
    get_application,
    get_application_answers,
    update_application_status,
    get_bot_guild_ids,
    update_application_question,
    set_application_notify_channel,
    get_application_notify_channel,
    delete_application,
    get_application_stats,
)
from dashboard.backend.bot_api import fetch_guild_text_channels, send_channel_message

application_router = APIRouter()
from dashboard.backend.template_context import global_template_context
templates = Jinja2Templates(directory="dashboard/backend/templates", context_processors=[global_template_context])


def _current_user(request: Request) -> dict | None:
    return request.session.get("user")


@application_router.get("/bewerbung/{guild_id}", response_class=HTMLResponse)
async def application_form_page(request: Request, guild_id: int):
    bot_guild_ids = await get_bot_guild_ids()
    if guild_id not in bot_guild_ids:
        return HTMLResponse("Dieser Server nutzt den Bot nicht (mehr).", status_code=404)

    config = await get_application_config(guild_id)
    if not config.enabled:
        return templates.TemplateResponse(request, "bewerbung_form.html", {
            "user": _current_user(request), "messages": [], "guild_id": guild_id,
            "config": config, "questions": [], "closed": True,
        })

    user = _current_user(request)
    if not user:
        request.session["post_login_redirect"] = f"/bewerbung/{guild_id}"
        return RedirectResponse("/login")

    already_applied = await has_pending_application(guild_id, int(user["discord_id"]))
    questions = await get_application_questions(guild_id)

    return templates.TemplateResponse(request, "bewerbung_form.html", {
        "user": user, "messages": [], "guild_id": guild_id,
        "config": config, "questions": questions, "closed": False,
        "already_applied": already_applied,
    })


@application_router.post("/bewerbung/{guild_id}")
async def application_form_submit(request: Request, guild_id: int):
    user = _current_user(request)
    if not user:
        return RedirectResponse(f"/bewerbung/{guild_id}")

    config = await get_application_config(guild_id)
    if not config.enabled:
        return RedirectResponse(f"/bewerbung/{guild_id}")

    if await has_pending_application(guild_id, int(user["discord_id"])):
        return RedirectResponse(f"/bewerbung/{guild_id}?error=already_applied")

    questions = await get_application_questions(guild_id)
    form = await request.form()

    answers = []
    for question in questions:
        answer_text = str(form.get(f"question_{question.id}", "")).strip()
        answers.append((question.question_text, answer_text))

    await create_application(guild_id, int(user["discord_id"]), user["username"], answers)

    notify_channel_id = await get_application_notify_channel(guild_id)
    if notify_channel_id:
        await send_channel_message(
            notify_channel_id,
            f"Neue Bewerbung von {user['username']} eingegangen — im Dashboard einsehbar.",
        )

    return templates.TemplateResponse(request, "bewerbung_form.html", {
        "user": user, "messages": [{"type": "success", "text": "Deine Bewerbung wurde übermittelt!"}],
        "guild_id": guild_id, "config": config, "questions": [], "closed": False, "already_applied": True,
    })


async def _require_guild_admin(request: Request, guild_id: int):
    """Nutzt dieselbe Zugriffsprüfung wie die restlichen Server-Dashboard-Seiten
    (siehe main.py: _require_guild_access) -- hier lokal importiert, um einen
    Ringimport zwischen main.py und diesem Modul zu vermeiden."""
    from dashboard.backend.main import _require_guild_access
    return await _require_guild_access(request, guild_id)


@application_router.get("/dashboard/{guild_id}/bewerbung/einstellungen", response_class=HTMLResponse)
async def application_settings_page(request: Request, guild_id: int):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied

    config = await get_application_config(guild_id)
    questions = await get_application_questions(guild_id)
    notify_channel_id = await get_application_notify_channel(guild_id)
    channels = await fetch_guild_text_channels(guild_id)
    stats = await get_application_stats(guild_id)
    return templates.TemplateResponse(request, "bewerbung_einstellungen.html", {
        "user": _current_user(request), "messages": [],
        "guild": {"id": guild_id, "name": guild["name"]},
        "config": config, "questions": questions,
        "notify_channel_id": notify_channel_id, "channels": channels, "stats": stats,
    })


@application_router.post("/dashboard/{guild_id}/bewerbung/einstellungen")
async def application_settings_save(request: Request, guild_id: int,
                                     enabled: str = Form(""), welcome_text: str = Form(""),
                                     notify_channel_id: int = Form(0)):
    denied, _guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    await set_application_config(guild_id, enabled == "on", welcome_text)
    await set_application_notify_channel(guild_id, notify_channel_id)
    return RedirectResponse(f"/dashboard/{guild_id}/bewerbung/einstellungen?saved=1", status_code=303)


@application_router.post("/dashboard/{guild_id}/bewerbung/fragen/{question_id}/bearbeiten")
async def application_question_edit(request: Request, guild_id: int, question_id: int,
                                     question_text: str = Form(...)):
    denied, _guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    if question_text.strip():
        await update_application_question(question_id, question_text.strip())
    return RedirectResponse(f"/dashboard/{guild_id}/bewerbung/einstellungen", status_code=303)


@application_router.post("/dashboard/{guild_id}/bewerbung/fragen")
async def application_question_add(request: Request, guild_id: int, question_text: str = Form(...)):
    denied, _guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    if question_text.strip():
        await add_application_question(guild_id, question_text.strip())
    return RedirectResponse(f"/dashboard/{guild_id}/bewerbung/einstellungen", status_code=303)


@application_router.post("/dashboard/{guild_id}/bewerbung/fragen/{question_id}/loeschen")
async def application_question_remove(request: Request, guild_id: int, question_id: int):
    denied, _guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    await remove_application_question(question_id)
    return RedirectResponse(f"/dashboard/{guild_id}/bewerbung/einstellungen", status_code=303)


@application_router.get("/dashboard/{guild_id}/bewerbungen", response_class=HTMLResponse)
async def applications_list_page(request: Request, guild_id: int, status: str = ""):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied

    applications = await get_applications_for_guild(guild_id)
    if status:
        applications = [a for a in applications if a.status == status]

    return templates.TemplateResponse(request, "bewerbung_liste.html", {
        "user": _current_user(request), "messages": [],
        "guild": {"id": guild_id, "name": guild["name"]},
        "applications": applications, "status": status,
    })


@application_router.post("/dashboard/{guild_id}/bewerbungen/{application_id}/loeschen")
async def application_delete(request: Request, guild_id: int, application_id: int):
    denied, _guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied
    await delete_application(application_id)
    return RedirectResponse(f"/dashboard/{guild_id}/bewerbungen", status_code=303)


@application_router.get("/dashboard/{guild_id}/bewerbungen/{application_id}", response_class=HTMLResponse)
async def application_detail_page(request: Request, guild_id: int, application_id: int):
    denied, guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied

    application = await get_application(application_id)
    if not application or application.guild_id != guild_id:
        return HTMLResponse("Bewerbung nicht gefunden.", status_code=404)

    answers = await get_application_answers(application_id)
    return templates.TemplateResponse(request, "bewerbung_detail.html", {
        "user": _current_user(request), "messages": [],
        "guild": {"id": guild_id, "name": guild["name"]},
        "application": application, "answers": answers,
    })


@application_router.post("/dashboard/{guild_id}/bewerbungen/{application_id}/status")
async def application_status_update(request: Request, guild_id: int, application_id: int,
                                     status: str = Form(...)):
    denied, _guild = await _require_guild_admin(request, guild_id)
    if denied:
        return denied

    user = _current_user(request)
    await update_application_status(application_id, status, int(user["discord_id"]))
    return RedirectResponse(f"/dashboard/{guild_id}/bewerbungen", status_code=303)
