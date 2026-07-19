"""
Gemeinsame Datenbank-Hilfsfunktionen, damit Moderation, Team-Management
und spätere Module (Tickets, Musik, ...) nicht denselben Code duplizieren.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.db import get_session
from bot.database.models import (
    GuildSettings, Punishment, TeamRank, TeamMember, TrustedUser, DashboardUser, BotGuild, Ticket,
    AdminUser, AdminPermission, GlobalAnnouncement, BotControlState,
    ApplicationConfig, ApplicationQuestion, Application, ApplicationAnswer,
)


async def get_or_create_guild_settings(session: AsyncSession, guild_id: int) -> GuildSettings:
    settings = await session.get(GuildSettings, guild_id)
    if settings is None:
        settings = GuildSettings(guild_id=guild_id)
        session.add(settings)
        await session.commit()
        await session.refresh(settings)
    return settings


async def get_guild_language(guild_id: int) -> str:
    async with get_session() as session:
        settings = await get_or_create_guild_settings(session, guild_id)
        return settings.language


async def log_punishment(
    guild_id: int,
    user_id: int,
    moderator_id: int,
    type_: str,
    reason: str,
    is_team_punishment: bool = False,
) -> Punishment:
    async with get_session() as session:
        punishment = Punishment(
            guild_id=guild_id,
            user_id=user_id,
            moderator_id=moderator_id,
            type=type_,
            reason=reason or "Kein Grund angegeben",
            is_team_punishment=is_team_punishment,
            created_at=dt.datetime.utcnow(),
        )
        session.add(punishment)
        await session.commit()
        await session.refresh(punishment)
        return punishment


async def get_user_punishments(guild_id: int, user_id: int, active_only: bool = True) -> list[Punishment]:
    async with get_session() as session:
        stmt = select(Punishment).where(Punishment.guild_id == guild_id, Punishment.user_id == user_id)
        if active_only:
            stmt = stmt.where(Punishment.active == True)  # noqa: E712
        stmt = stmt.order_by(Punishment.created_at.desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def deactivate_punishment(punishment_id: int) -> bool:
    async with get_session() as session:
        punishment = await session.get(Punishment, punishment_id)
        if punishment is None:
            return False
        punishment.active = False
        await session.commit()
        return True


async def get_team_ranks(guild_id: int) -> list[TeamRank]:
    """Ränge aufsteigend sortiert (0 = niedrigster Rang)."""
    async with get_session() as session:
        stmt = select(TeamRank).where(TeamRank.guild_id == guild_id).order_by(TeamRank.position.asc())
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_team_member(guild_id: int, user_id: int) -> TeamMember | None:
    async with get_session() as session:
        stmt = select(TeamMember).where(TeamMember.guild_id == guild_id, TeamMember.user_id == user_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def get_all_team_members(guild_id: int) -> list[TeamMember]:
    async with get_session() as session:
        stmt = select(TeamMember).where(TeamMember.guild_id == guild_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def upsert_team_member(guild_id: int, user_id: int, rank_id: int | None) -> TeamMember:
    async with get_session() as session:
        stmt = select(TeamMember).where(TeamMember.guild_id == guild_id, TeamMember.user_id == user_id)
        result = await session.execute(stmt)
        member = result.scalar_one_or_none()
        if member is None:
            member = TeamMember(guild_id=guild_id, user_id=user_id, current_rank_id=rank_id)
            session.add(member)
        else:
            member.current_rank_id = rank_id
        await session.commit()
        await session.refresh(member)
        return member


async def remove_team_member(guild_id: int, user_id: int) -> bool:
    async with get_session() as session:
        stmt = select(TeamMember).where(TeamMember.guild_id == guild_id, TeamMember.user_id == user_id)
        result = await session.execute(stmt)
        member = result.scalar_one_or_none()
        if member is None:
            return False
        await session.delete(member)
        await session.commit()
        return True


# ---------- Anti-Nuke / Anti-Spam ----------
#
# WICHTIG: is_trusted_user() und get_security_settings() werden bei JEDER
# Nachricht auf dem Server aufgerufen (siehe anti_spam.py on_message).
# Ohne Zwischenspeicher würde das bei aktiven Servern tausende
# Datenbank-Anfragen pro Tag bedeuten und (v.a. bei Neon mit begrenzten
# gleichzeitigen Verbindungen) auch andere Befehle ausbremsen.
# Daher: ein einfacher In-Memory-Cache pro Server, der bei jeder Änderung
# (Toggle, Trust/Untrust) sofort mit aktualisiert wird -- er wird also nie
# "veraltet" ausgeliefert, nur beim allerersten Zugriff pro Server einmal
# aus der Datenbank geladen.
_security_cache: dict[int, dict] = {}


async def _get_or_load_security_cache(guild_id: int) -> dict:
    if guild_id not in _security_cache:
        async with get_session() as session:
            settings = await get_or_create_guild_settings(session, guild_id)
            stmt = select(TrustedUser.user_id).where(TrustedUser.guild_id == guild_id)
            result = await session.execute(stmt)
            trusted_ids = set(result.scalars().all())
        _security_cache[guild_id] = {
            "anti_nuke": settings.anti_nuke_enabled,
            "anti_spam": settings.anti_spam_enabled,
            "trusted_ids": trusted_ids,
        }
    return _security_cache[guild_id]


async def is_trusted_user(guild_id: int, user_id: int) -> bool:
    cache = await _get_or_load_security_cache(guild_id)
    return user_id in cache["trusted_ids"]


async def add_trusted_user(guild_id: int, user_id: int, added_by: int) -> bool:
    if await is_trusted_user(guild_id, user_id):
        return False
    async with get_session() as session:
        session.add(TrustedUser(guild_id=guild_id, user_id=user_id, added_by=added_by))
        await session.commit()
    _security_cache[guild_id]["trusted_ids"].add(user_id)
    return True


async def remove_trusted_user(guild_id: int, user_id: int) -> bool:
    async with get_session() as session:
        stmt = select(TrustedUser).where(TrustedUser.guild_id == guild_id, TrustedUser.user_id == user_id)
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()
        if entry is None:
            return False
        await session.delete(entry)
        await session.commit()
    _security_cache.get(guild_id, {}).get("trusted_ids", set()).discard(user_id)
    return True


async def get_trusted_users(guild_id: int) -> list[TrustedUser]:
    async with get_session() as session:
        stmt = select(TrustedUser).where(TrustedUser.guild_id == guild_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def set_anti_nuke_enabled(guild_id: int, enabled: bool) -> None:
    async with get_session() as session:
        settings = await get_or_create_guild_settings(session, guild_id)
        settings.anti_nuke_enabled = enabled
        await session.commit()
    cache = await _get_or_load_security_cache(guild_id)
    cache["anti_nuke"] = enabled


async def set_anti_spam_enabled(guild_id: int, enabled: bool) -> None:
    async with get_session() as session:
        settings = await get_or_create_guild_settings(session, guild_id)
        settings.anti_spam_enabled = enabled
        await session.commit()
    cache = await _get_or_load_security_cache(guild_id)
    cache["anti_spam"] = enabled


async def get_security_settings(guild_id: int) -> tuple[bool, bool]:
    """Gibt (anti_nuke_enabled, anti_spam_enabled) zurück. Nutzt den Cache,
    fragt also NICHT bei jedem Aufruf die Datenbank ab (siehe Hinweis oben)."""
    cache = await _get_or_load_security_cache(guild_id)
    return cache["anti_nuke"], cache["anti_spam"]


# ---------- Dashboard: User & Bot-Server-Sync ----------

async def upsert_dashboard_user(discord_id: int, username: str, avatar_hash: str) -> DashboardUser:
    """Legt beim ersten Login eine neue Dashboard-Identität an (mit eigener UUID)
    oder aktualisiert bei jedem weiteren Login Username/Avatar/last_login_at."""
    import uuid
    async with get_session() as session:
        stmt = select(DashboardUser).where(DashboardUser.discord_id == discord_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        now = dt.datetime.utcnow()
        if user is None:
            user = DashboardUser(
                id=str(uuid.uuid4()),
                discord_id=discord_id,
                username=username,
                avatar_hash=avatar_hash,
                first_login_at=now,
                last_login_at=now,
            )
            session.add(user)
        else:
            user.username = username
            user.avatar_hash = avatar_hash
            user.last_login_at = now
        await session.commit()
        await session.refresh(user)
        return user


async def upsert_bot_guild(guild_id: int, name: str, icon_hash: str, member_count: int) -> None:
    async with get_session() as session:
        guild = await session.get(BotGuild, guild_id)
        now = dt.datetime.utcnow()
        if guild is None:
            session.add(BotGuild(guild_id=guild_id, name=name, icon_hash=icon_hash,
                                  member_count=member_count, updated_at=now))
        else:
            guild.name = name
            guild.icon_hash = icon_hash
            guild.member_count = member_count
            guild.updated_at = now
        await session.commit()


async def remove_bot_guild(guild_id: int) -> None:
    async with get_session() as session:
        guild = await session.get(BotGuild, guild_id)
        if guild is not None:
            await session.delete(guild)
            await session.commit()


async def is_bot_in_guild(guild_id: int) -> bool:
    async with get_session() as session:
        return await session.get(BotGuild, guild_id) is not None


async def get_bot_guild_ids() -> set[int]:
    async with get_session() as session:
        result = await session.execute(select(BotGuild.guild_id))
        return set(result.scalars().all())


async def save_guild_settings_from_dashboard(
    guild_id: int, language: str, mod_log_channel_id: int, punishment_log_channel_id: int,
    announcement_channel_id: int,
) -> None:
    async with get_session() as session:
        settings = await get_or_create_guild_settings(session, guild_id)
        settings.language = language
        settings.mod_log_channel_id = mod_log_channel_id
        settings.punishment_log_channel_id = punishment_log_channel_id
        settings.announcement_channel_id = announcement_channel_id
        await session.commit()


# ---------- Tickets ----------

async def get_open_ticket_for_user(guild_id: int, user_id: int) -> Ticket | None:
    async with get_session() as session:
        stmt = select(Ticket).where(
            Ticket.guild_id == guild_id, Ticket.creator_id == user_id, Ticket.status == "open",
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def create_ticket(guild_id: int, channel_id: int, creator_id: int, design: str) -> Ticket:
    async with get_session() as session:
        ticket = Ticket(guild_id=guild_id, channel_id=channel_id, creator_id=creator_id, design=design)
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        return ticket


async def get_ticket_by_channel(channel_id: int) -> Ticket | None:
    async with get_session() as session:
        stmt = select(Ticket).where(Ticket.channel_id == channel_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def close_ticket(channel_id: int, claimed_by: int = 0) -> bool:
    async with get_session() as session:
        stmt = select(Ticket).where(Ticket.channel_id == channel_id)
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        if ticket is None:
            return False
        ticket.status = "closed"
        ticket.closed_at = dt.datetime.utcnow()
        if claimed_by:
            ticket.claimed_by = claimed_by
        await session.commit()
        return True


async def count_open_tickets(guild_id: int) -> int:
    async with get_session() as session:
        stmt = select(Ticket).where(Ticket.guild_id == guild_id, Ticket.status == "open")
        result = await session.execute(stmt)
        return len(result.scalars().all())


# ---------- Kurzlebiger Cache für sehr häufig abgefragte Settings ----------
#
# Manche Listener (z.B. Warteraum: on_voice_state_update) feuern bei JEDER
# Sprachkanal-Aktivität auf JEDEM Server -- ohne Cache wäre das dieselbe
# Datenbank-Last wie beim ungecachten Anti-Spam-Problem (siehe oben).
# Bewusst ein einfacher, kurzer TTL-Cache (15s) statt Invalidierung-bei-jedem-
# Schreibzugriff: die betroffenen Felder (Warteraum-Kanäle, Sprache) ändern
# sich selten, ein paar Sekunden Verzögerung nach einer Änderung ist
# unkritisch, macht den Code aber deutlich einfacher als eine vollständige
# Invalidierungs-Logik an jeder einzelnen Schreibstelle nachzuziehen.
_settings_snapshot_cache: dict[int, tuple[float, dict]] = {}
_SETTINGS_CACHE_TTL_SECONDS = 15


async def get_guild_settings_snapshot(guild_id: int) -> dict:
    """Gibt ein Dict mit den gängigsten GuildSettings-Feldern zurück, aus
    einem kurzlebigen Cache (siehe Hinweis oben). Für Schreibvorgänge oder
    wenn absolute Aktualität nötig ist, weiterhin get_or_create_guild_settings
    direkt verwenden."""
    now = dt.datetime.utcnow().timestamp()
    cached = _settings_snapshot_cache.get(guild_id)
    if cached and now - cached[0] < _SETTINGS_CACHE_TTL_SECONDS:
        return cached[1]

    async with get_session() as session:
        settings = await get_or_create_guild_settings(session, guild_id)
        snapshot = {
            "language": settings.language,
            "waiting_room_voice_channel_id": settings.waiting_room_voice_channel_id,
            "waiting_room_notify_channel_id": settings.waiting_room_notify_channel_id,
            "ticket_category_id": settings.ticket_category_id,
            "mod_log_channel_id": settings.mod_log_channel_id,
        }
    _settings_snapshot_cache[guild_id] = (now, snapshot)
    return snapshot


# ---------- Admin-Panel ----------

async def get_admin_user_by_username(username: str) -> AdminUser | None:
    async with get_session() as session:
        stmt = select(AdminUser).where(AdminUser.username == username)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def get_admin_user_by_id(admin_id: int) -> AdminUser | None:
    async with get_session() as session:
        return await session.get(AdminUser, admin_id)


async def create_admin_user(username: str, password_hash: str, is_superadmin: bool = False) -> AdminUser:
    async with get_session() as session:
        user = AdminUser(username=username, password_hash=password_hash, is_superadmin=is_superadmin)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def count_admin_users() -> int:
    async with get_session() as session:
        result = await session.execute(select(AdminUser))
        return len(result.scalars().all())


async def update_admin_last_login(admin_id: int) -> None:
    async with get_session() as session:
        user = await session.get(AdminUser, admin_id)
        if user:
            user.last_login_at = dt.datetime.utcnow()
            await session.commit()


async def list_admin_users() -> list[AdminUser]:
    async with get_session() as session:
        result = await session.execute(select(AdminUser))
        return list(result.scalars().all())


async def get_admin_permissions(admin_id: int) -> set[str]:
    async with get_session() as session:
        stmt = select(AdminPermission.permission_key).where(AdminPermission.admin_user_id == admin_id)
        result = await session.execute(stmt)
        return set(result.scalars().all())


async def grant_admin_permission(admin_id: int, permission_key: str, granted_by: int) -> None:
    async with get_session() as session:
        stmt = select(AdminPermission).where(
            AdminPermission.admin_user_id == admin_id, AdminPermission.permission_key == permission_key,
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing:
            return
        session.add(AdminPermission(admin_user_id=admin_id, permission_key=permission_key, granted_by=granted_by))
        await session.commit()


async def revoke_admin_permission(admin_id: int, permission_key: str) -> None:
    async with get_session() as session:
        stmt = select(AdminPermission).where(
            AdminPermission.admin_user_id == admin_id, AdminPermission.permission_key == permission_key,
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing:
            await session.delete(existing)
            await session.commit()


async def get_bot_control_state() -> BotControlState:
    async with get_session() as session:
        state = await session.get(BotControlState, 1)
        if state is None:
            state = BotControlState(id=1)
            session.add(state)
            await session.commit()
            await session.refresh(state)
        return state


async def set_maintenance_mode(enabled: bool, reason: str, admin_id: int) -> None:
    async with get_session() as session:
        state = await session.get(BotControlState, 1)
        if state is None:
            state = BotControlState(id=1)
            session.add(state)
        state.maintenance_mode = enabled
        state.maintenance_reason = reason
        state.updated_by_admin_id = admin_id
        state.updated_at = dt.datetime.utcnow()
        await session.commit()


async def log_global_announcement(message: str, guild_count: int, admin_id: int) -> None:
    async with get_session() as session:
        session.add(GlobalAnnouncement(sent_by_admin_id=admin_id, message=message, guild_count=guild_count))
        await session.commit()


async def get_all_bot_guilds() -> list[BotGuild]:
    async with get_session() as session:
        result = await session.execute(select(BotGuild))
        return list(result.scalars().all())


# ---------- Bewerbungssystem ----------

async def get_application_config(guild_id: int) -> ApplicationConfig:
    async with get_session() as session:
        config = await session.get(ApplicationConfig, guild_id)
        if config is None:
            config = ApplicationConfig(guild_id=guild_id)
            session.add(config)
            await session.commit()
            await session.refresh(config)
        return config


async def set_application_config(guild_id: int, enabled: bool, welcome_text: str) -> None:
    async with get_session() as session:
        config = await session.get(ApplicationConfig, guild_id)
        if config is None:
            config = ApplicationConfig(guild_id=guild_id)
            session.add(config)
        config.enabled = enabled
        config.welcome_text = welcome_text
        await session.commit()


async def get_application_questions(guild_id: int) -> list[ApplicationQuestion]:
    async with get_session() as session:
        stmt = select(ApplicationQuestion).where(
            ApplicationQuestion.guild_id == guild_id
        ).order_by(ApplicationQuestion.position.asc())
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def add_application_question(guild_id: int, question_text: str) -> ApplicationQuestion:
    async with get_session() as session:
        existing = await get_application_questions(guild_id)
        next_position = max((q.position for q in existing), default=-1) + 1
        question = ApplicationQuestion(guild_id=guild_id, question_text=question_text, position=next_position)
        session.add(question)
        await session.commit()
        await session.refresh(question)
        return question


async def remove_application_question(question_id: int) -> bool:
    async with get_session() as session:
        question = await session.get(ApplicationQuestion, question_id)
        if question is None:
            return False
        await session.delete(question)
        await session.commit()
        return True


async def has_pending_application(guild_id: int, discord_id: int) -> bool:
    async with get_session() as session:
        stmt = select(Application).where(
            Application.guild_id == guild_id,
            Application.applicant_discord_id == discord_id,
            Application.status == "pending",
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None


async def create_application(guild_id: int, discord_id: int, username: str,
                              answers: list[tuple[str, str]]) -> Application:
    """answers: Liste von (Frage, Antwort)-Paaren."""
    async with get_session() as session:
        application = Application(guild_id=guild_id, applicant_discord_id=discord_id, applicant_username=username)
        session.add(application)
        await session.commit()
        await session.refresh(application)

        for question_text, answer_text in answers:
            session.add(ApplicationAnswer(
                application_id=application.id, question_text=question_text, answer_text=answer_text,
            ))
        await session.commit()
        return application


async def get_applications_for_guild(guild_id: int, status: str | None = None) -> list[Application]:
    async with get_session() as session:
        stmt = select(Application).where(Application.guild_id == guild_id)
        if status:
            stmt = stmt.where(Application.status == status)
        stmt = stmt.order_by(Application.submitted_at.desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_application(application_id: int) -> Application | None:
    async with get_session() as session:
        return await session.get(Application, application_id)


async def get_application_answers(application_id: int) -> list[ApplicationAnswer]:
    async with get_session() as session:
        stmt = select(ApplicationAnswer).where(ApplicationAnswer.application_id == application_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def update_application_status(application_id: int, status: str, reviewed_by: int) -> None:
    async with get_session() as session:
        application = await session.get(Application, application_id)
        if application:
            application.status = status
            application.reviewed_by = reviewed_by
            application.reviewed_at = dt.datetime.utcnow()
            await session.commit()
