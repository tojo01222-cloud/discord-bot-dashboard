"""
Gemeinsame Datenbank-Hilfsfunktionen, damit Moderation, Team-Management
und spätere Module (Tickets, Musik, ...) nicht denselben Code duplizieren.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import config
from bot.database.db import get_session
from bot.database.models import (
    GuildSettings, Punishment, TeamRank, TeamMember, TrustedUser, DashboardUser, BotGuild, Ticket,
    TicketCategory,
    AdminUser, AdminPermission, GlobalAnnouncement, BotControlState,
    ApplicationConfig, ApplicationQuestion, Application, ApplicationAnswer,
    LevelXP, LevelRoleReward, InviteRecord, InviteJoin, Giveaway, GiveawayEntry,
    PermissionGroup, PermissionGroupEntry, AdminUserGroup, ApplicationNotifyChannel,
    AntiExemption, AntiWerbungStrike, RegisterAccessRole,
    NewsPost, StaffNote,
    AdConfig, Partner, ReactionRole, SuggestionConfig, Suggestion,
    BirthdayConfig, Birthday, EconomyBalance, ShopItem,
    WelcomeConfig, TimedAutorole, VerificationConfig,
    Poll, PollVote, StickyMessage, BannedWord, VoiceTime, ServerBackup,
    ScheduledEvent, DashboardAuditLog, DailyActivity,
    GlobalBlocklist, AdminLoginHistory,
    ErrorLog, ApiCallStat, GuildTag, GuildAdminNote, ChangelogEntry,
    FeatureFlag, Feedback, ScheduledMaintenance, RoleTemplate, TicketPanel,
)
import json as _json


async def get_or_create_guild_settings(session: AsyncSession, guild_id: int) -> GuildSettings:
    settings = await session.get(GuildSettings, guild_id)
    if settings is None:
        # Bug-Fix: Config.DEFAULT_LANGUAGE wurde bisher nirgends tatsächlich
        # gelesen (totes .env-Setting) -- neue Server bekamen immer die
        # Spalten-Default-Sprache. Jetzt wird der konfigurierte Standard beim
        # allerersten Anlegen der Server-Einstellungen wirklich angewendet.
        settings = GuildSettings(guild_id=guild_id, language=config.DEFAULT_LANGUAGE)
        session.add(settings)
        await session.commit()
        await session.refresh(settings)
    return settings


async def get_guild_language(guild_id: int) -> str:
    async with get_session() as session:
        settings = await get_or_create_guild_settings(session, guild_id)
        return settings.language


async def set_guild_language(guild_id: int, language: str) -> None:
    async with get_session() as session:
        settings = await get_or_create_guild_settings(session, guild_id)
        settings.language = language
        await session.commit()
    _settings_snapshot_cache.pop(guild_id, None)


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


async def get_guild_punishments(guild_id: int, active_only: bool = True, limit: int = 100) -> list[Punishment]:
    """Alle Strafen eines Servers (nicht nur eines Users) -- fürs Dashboard."""
    async with get_session() as session:
        stmt = select(Punishment).where(Punishment.guild_id == guild_id)
        if active_only:
            stmt = stmt.where(Punishment.active == True)  # noqa: E712
        stmt = stmt.order_by(Punishment.created_at.desc()).limit(limit)
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


async def add_team_rank(guild_id: int, role_id: int) -> TeamRank:
    """Fügt einen Team-Rang am Ende der Hierarchie hinzu (dieselbe Logik wie /teamrank add)."""
    async with get_session() as session:
        existing = (await session.execute(
            select(TeamRank).where(TeamRank.guild_id == guild_id)
        )).scalars().all()
        next_position = max((r.position for r in existing), default=-1) + 1
        rank = TeamRank(guild_id=guild_id, role_id=role_id, position=next_position)
        session.add(rank)
        await session.commit()
        await session.refresh(rank)
        return rank


async def remove_team_rank(rank_id: int) -> bool:
    async with get_session() as session:
        rank = await session.get(TeamRank, rank_id)
        if rank is None:
            return False
        await session.delete(rank)
        await session.commit()
        return True


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
# (Toggle, Trust/Untrust) INNERHALB DESSELBEN PROZESSES sofort mit aktualisiert
# wird. WICHTIG: Bot und Dashboard laufen als komplett getrennte Prozesse
# (unterschiedliche Server!) ohne gemeinsamen Arbeitsspeicher -- eine Änderung
# über das Dashboard (z.B. der neue Anti-Nuke/-Spam-Schalter in den
# Server-Einstellungen) kann den Cache im BOT-Prozess nicht direkt
# invalidieren. Deshalb zusätzlich ein TTL von 60s, damit solche
# prozessübergreifenden Änderungen spätestens nach einer Minute ankommen,
# statt bis zum nächsten Bot-Neustart veraltet zu bleiben.
_security_cache: dict[int, tuple[float, dict]] = {}
_SECURITY_CACHE_TTL_SECONDS = 60


async def _get_or_load_security_cache(guild_id: int) -> dict:
    now = dt.datetime.utcnow().timestamp()
    cached = _security_cache.get(guild_id)
    if cached and now - cached[0] < _SECURITY_CACHE_TTL_SECONDS:
        return cached[1]

    async with get_session() as session:
        settings = await get_or_create_guild_settings(session, guild_id)
        stmt = select(TrustedUser.user_id).where(TrustedUser.guild_id == guild_id)
        result = await session.execute(stmt)
        trusted_ids = set(result.scalars().all())
    data = {
        "anti_nuke": settings.anti_nuke_enabled,
        "anti_spam": settings.anti_spam_enabled,
        "anti_hack": settings.anti_hack_enabled,
        "anti_werbung": settings.anti_werbung_enabled,
        "trusted_ids": trusted_ids,
    }
    _security_cache[guild_id] = (now, data)
    return data


async def is_trusted_user(guild_id: int, user_id: int) -> bool:
    cache = await _get_or_load_security_cache(guild_id)
    return user_id in cache["trusted_ids"]


async def add_trusted_user(guild_id: int, user_id: int, added_by: int) -> bool:
    if await is_trusted_user(guild_id, user_id):
        return False
    async with get_session() as session:
        session.add(TrustedUser(guild_id=guild_id, user_id=user_id, added_by=added_by))
        await session.commit()
    if guild_id in _security_cache:
        _security_cache[guild_id][1]["trusted_ids"].add(user_id)
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
    if guild_id in _security_cache:
        _security_cache[guild_id][1]["trusted_ids"].discard(user_id)
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


async def set_anti_hack_enabled(guild_id: int, enabled: bool) -> None:
    async with get_session() as session:
        settings = await get_or_create_guild_settings(session, guild_id)
        settings.anti_hack_enabled = enabled
        await session.commit()
    cache = await _get_or_load_security_cache(guild_id)
    cache["anti_hack"] = enabled


async def set_anti_werbung_enabled(guild_id: int, enabled: bool) -> None:
    async with get_session() as session:
        settings = await get_or_create_guild_settings(session, guild_id)
        settings.anti_werbung_enabled = enabled
        await session.commit()
    cache = await _get_or_load_security_cache(guild_id)
    cache["anti_werbung"] = enabled


async def get_anti_hack_enabled(guild_id: int) -> bool:
    cache = await _get_or_load_security_cache(guild_id)
    return cache["anti_hack"]


async def get_anti_werbung_enabled(guild_id: int) -> bool:
    cache = await _get_or_load_security_cache(guild_id)
    return cache["anti_werbung"]


# ---------- Anti-Hack / Anti-Werbung: gemeinsame Ausnahmeliste ----------

async def add_anti_exemption(guild_id: int, feature: str, target_type: str, target_id: int, added_by: int) -> bool:
    if await is_anti_exempt(guild_id, feature, target_type, target_id):
        return False
    async with get_session() as session:
        session.add(AntiExemption(guild_id=guild_id, feature=feature, target_type=target_type,
                                   target_id=target_id, added_by=added_by))
        await session.commit()
    return True


async def get_anti_exemptions(guild_id: int, feature: str) -> list[AntiExemption]:
    async with get_session() as session:
        stmt = select(AntiExemption).where(AntiExemption.guild_id == guild_id, AntiExemption.feature == feature)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def is_anti_exempt(guild_id: int, feature: str, target_type: str, target_id: int) -> bool:
    async with get_session() as session:
        stmt = select(AntiExemption).where(
            AntiExemption.guild_id == guild_id, AntiExemption.feature == feature,
            AntiExemption.target_type == target_type, AntiExemption.target_id == target_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None


async def remove_anti_exemption(guild_id: int, feature: str, target_type: str, target_id: int) -> bool:
    async with get_session() as session:
        stmt = select(AntiExemption).where(
            AntiExemption.guild_id == guild_id, AntiExemption.feature == feature,
            AntiExemption.target_type == target_type, AntiExemption.target_id == target_id,
        )
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()
        if entry is None:
            return False
        await session.delete(entry)
        await session.commit()
        return True


# ---------- Anti-Werbung: Eskalationszähler ----------

async def bump_anti_werbung_strike(guild_id: int, user_id: int) -> int:
    """Erhöht den Verstoßzähler eines Users um 1 und gibt den neuen Stand zurück."""
    async with get_session() as session:
        stmt = select(AntiWerbungStrike).where(
            AntiWerbungStrike.guild_id == guild_id, AntiWerbungStrike.user_id == user_id,
        )
        result = await session.execute(stmt)
        strike = result.scalar_one_or_none()
        if strike is None:
            strike = AntiWerbungStrike(guild_id=guild_id, user_id=user_id, count=0)
            session.add(strike)
        strike.count += 1
        strike.last_at = dt.datetime.utcnow()
        await session.commit()
        return strike.count


async def reset_anti_werbung_strikes(guild_id: int, user_id: int) -> None:
    async with get_session() as session:
        stmt = select(AntiWerbungStrike).where(
            AntiWerbungStrike.guild_id == guild_id, AntiWerbungStrike.user_id == user_id,
        )
        result = await session.execute(stmt)
        strike = result.scalar_one_or_none()
        if strike is not None:
            strike.count = 0
            await session.commit()


# ---------- Strafregister: Rollen mit Einsichtsrecht ----------

async def grant_register_access(guild_id: int, role_id: int, granted_by: int) -> bool:
    async with get_session() as session:
        stmt = select(RegisterAccessRole).where(
            RegisterAccessRole.guild_id == guild_id, RegisterAccessRole.role_id == role_id,
        )
        result = await session.execute(stmt)
        if result.scalar_one_or_none() is not None:
            return False
        session.add(RegisterAccessRole(guild_id=guild_id, role_id=role_id, granted_by=granted_by))
        await session.commit()
        return True


async def revoke_register_access(guild_id: int, role_id: int) -> bool:
    async with get_session() as session:
        stmt = select(RegisterAccessRole).where(
            RegisterAccessRole.guild_id == guild_id, RegisterAccessRole.role_id == role_id,
        )
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()
        if entry is None:
            return False
        await session.delete(entry)
        await session.commit()
        return True


async def get_register_access_roles(guild_id: int) -> list[RegisterAccessRole]:
    async with get_session() as session:
        stmt = select(RegisterAccessRole).where(RegisterAccessRole.guild_id == guild_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())


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
    announcement_channel_id: int, ticket_category_id: int = 0,
    waiting_room_voice_channel_id: int = 0, waiting_room_notify_channel_id: int = 0,
    autorole_id: int = 0, anti_nuke_enabled: bool = True, anti_spam_enabled: bool = True,
    music_bound_voice_channel_id: int = 0,
    autorole_bot_id: int = 0, autorole_admin_id: int = 0,
    anti_hack_enabled: bool = False, anti_werbung_enabled: bool = False,
) -> None:
    async with get_session() as session:
        settings = await get_or_create_guild_settings(session, guild_id)
        settings.language = language
        settings.mod_log_channel_id = mod_log_channel_id
        settings.punishment_log_channel_id = punishment_log_channel_id
        settings.announcement_channel_id = announcement_channel_id
        settings.ticket_category_id = ticket_category_id
        settings.waiting_room_voice_channel_id = waiting_room_voice_channel_id
        settings.waiting_room_notify_channel_id = waiting_room_notify_channel_id
        settings.autorole_id = autorole_id
        settings.autorole_bot_id = autorole_bot_id
        settings.autorole_admin_id = autorole_admin_id
        settings.anti_nuke_enabled = anti_nuke_enabled
        settings.anti_spam_enabled = anti_spam_enabled
        settings.anti_hack_enabled = anti_hack_enabled
        settings.anti_werbung_enabled = anti_werbung_enabled
        settings.music_bound_voice_channel_id = music_bound_voice_channel_id
        await session.commit()
    # Hinweis: Dashboard und Bot sind getrennte Prozesse ohne gemeinsamen
    # Speicher -- dieses .pop() wirkt nur auf den (hier ungenutzten) lokalen
    # Cache des Dashboard-Prozesses. Dass die Änderung auch im Bot-Prozess
    # ankommt, übernimmt der 60s-TTL in _get_or_load_security_cache().
    _security_cache.pop(guild_id, None)
    _settings_snapshot_cache.pop(guild_id, None)


# ---------- Tickets ----------

async def get_open_ticket_for_user(guild_id: int, user_id: int) -> Ticket | None:
    async with get_session() as session:
        stmt = select(Ticket).where(
            Ticket.guild_id == guild_id, Ticket.creator_id == user_id, Ticket.status == "open",
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def create_ticket(guild_id: int, channel_id: int, creator_id: int, design: str,
                         category_id: int = 0) -> Ticket:
    async with get_session() as session:
        ticket = Ticket(guild_id=guild_id, channel_id=channel_id, creator_id=creator_id,
                         design=design, category_id=category_id)
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


async def claim_ticket(channel_id: int, user_id: int) -> bool:
    """Markiert ein OFFENES Ticket als von user_id übernommen (/ticketclaim) --
    unabhängig vom claimed_by-Feld, das close_ticket beim Schließen setzt."""
    async with get_session() as session:
        stmt = select(Ticket).where(Ticket.channel_id == channel_id)
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        if ticket is None:
            return False
        ticket.claimed_by = user_id
        await session.commit()
        return True


async def count_open_tickets(guild_id: int) -> int:
    async with get_session() as session:
        stmt = select(Ticket).where(Ticket.guild_id == guild_id, Ticket.status == "open")
        result = await session.execute(stmt)
        return len(result.scalars().all())


async def get_tickets_for_guild(guild_id: int, limit: int = 100) -> list[Ticket]:
    async with get_session() as session:
        stmt = select(Ticket).where(Ticket.guild_id == guild_id).order_by(Ticket.created_at.desc()).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())


# ---------- Ticket-Typen (verschiedene Ticket-"Kategorien" zur Auswahl) ----------

async def get_ticket_categories(guild_id: int) -> list[TicketCategory]:
    async with get_session() as session:
        stmt = (
            select(TicketCategory)
            .where(TicketCategory.guild_id == guild_id)
            .order_by(TicketCategory.position, TicketCategory.id)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_ticket_category(category_id: int) -> TicketCategory | None:
    async with get_session() as session:
        return await session.get(TicketCategory, category_id)


async def get_ticket_category_by_name(guild_id: int, name: str) -> TicketCategory | None:
    async with get_session() as session:
        stmt = select(TicketCategory).where(
            TicketCategory.guild_id == guild_id,
            TicketCategory.name.ilike(name),
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def create_ticket_category(
    guild_id: int, name: str, emoji: str = "🎫", description: str = "",
    color_hex: str = "", channel_category_id: int = 0,
    max_concurrent: int = 0, ping_role_id: int = 0,
) -> TicketCategory:
    async with get_session() as session:
        existing = await session.execute(
            select(TicketCategory).where(TicketCategory.guild_id == guild_id)
        )
        next_position = len(existing.scalars().all())
        category = TicketCategory(
            guild_id=guild_id, name=name, emoji=emoji or "🎫", description=description,
            color_hex=color_hex, channel_category_id=channel_category_id, position=next_position,
            max_concurrent=max_concurrent, ping_role_id=ping_role_id,
        )
        session.add(category)
        await session.commit()
        await session.refresh(category)
        return category


async def update_ticket_category(
    category_id: int, *, emoji: str | None = None, description: str | None = None,
    color_hex: str | None = None, channel_category_id: int | None = None,
    max_concurrent: int | None = None, ping_role_id: int | None = None,
) -> TicketCategory | None:
    async with get_session() as session:
        category = await session.get(TicketCategory, category_id)
        if category is None:
            return None
        if emoji is not None:
            category.emoji = emoji
        if description is not None:
            category.description = description
        if color_hex is not None:
            category.color_hex = color_hex
        if channel_category_id is not None:
            category.channel_category_id = channel_category_id
        if max_concurrent is not None:
            category.max_concurrent = max_concurrent
        if ping_role_id is not None:
            category.ping_role_id = ping_role_id
        await session.commit()
        await session.refresh(category)
        return category


async def count_open_tickets_by_category(category_id: int) -> int:
    """Wie viele Tickets dieser Art gerade offen sind -- fürs Auslastungs-Panel
    und die Kapazitätsprüfung beim Erstellen."""
    async with get_session() as session:
        stmt = select(Ticket).where(Ticket.category_id == category_id, Ticket.status == "open")
        result = await session.execute(stmt)
        return len(result.scalars().all())


async def delete_ticket_category(category_id: int) -> bool:
    async with get_session() as session:
        category = await session.get(TicketCategory, category_id)
        if category is None:
            return False
        await session.delete(category)
        await session.commit()
        return True


# ---------- Musik: zuletzt aktiver Radiosender persistieren ----------
#
# Damit der Bot nach /stop, einem Kick aus dem Sprachkanal oder einem
# kompletten Neustart automatisch beim (Wieder-)Beitritt zum gebundenen
# Musikkanal denselben Sender fortsetzt, ohne dass /radio erneut nötig ist.

async def set_music_last_genre(guild_id: int, genre: str) -> None:
    async with get_session() as session:
        settings = await get_or_create_guild_settings(session, guild_id)
        settings.music_last_genre = genre
        await session.commit()


async def get_music_last_genre(guild_id: int) -> str:
    async with get_session() as session:
        settings = await get_or_create_guild_settings(session, guild_id)
        return settings.music_last_genre


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
            "waiting_room_message": settings.waiting_room_message,
            "ticket_category_id": settings.ticket_category_id,
            "mod_log_channel_id": settings.mod_log_channel_id,
            "autorole_id": settings.autorole_id,
            "autorole_bot_id": settings.autorole_bot_id,
            "autorole_admin_id": settings.autorole_admin_id,
        }
    _settings_snapshot_cache[guild_id] = (now, snapshot)
    return snapshot


# ---------- Auto-Role (drei Ziele: alle Mitglieder, Bots/Apps, Administratoren) ----------

AUTOROLE_TARGETS = ("alle", "bots", "admins")


async def set_autorole(guild_id: int, target: str, role_id: int) -> None:
    """target: 'alle' (menschliche Mitglieder), 'bots' (Bot-/App-Accounts) oder
    'admins' (automatisch synchronisiert mit Administrator-Rechten)."""
    async with get_session() as session:
        settings = await get_or_create_guild_settings(session, guild_id)
        if target == "alle":
            settings.autorole_id = role_id
        elif target == "bots":
            settings.autorole_bot_id = role_id
        elif target == "admins":
            settings.autorole_admin_id = role_id
        await session.commit()
    _settings_snapshot_cache.pop(guild_id, None)


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


async def get_recent_announcements(limit: int = 20) -> list[GlobalAnnouncement]:
    async with get_session() as session:
        stmt = select(GlobalAnnouncement).order_by(GlobalAnnouncement.sent_at.desc()).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_global_stats() -> dict:
    """Aggregierte Statistiken über alle Server hinweg, fürs Admin-Panel."""
    async with get_session() as session:
        guild_count = len((await session.execute(select(BotGuild))).scalars().all())
        total_members = sum(g.member_count for g in (await session.execute(select(BotGuild))).scalars().all())
        punishment_count = len((await session.execute(select(Punishment))).scalars().all())
        open_ticket_count = len((await session.execute(
            select(Ticket).where(Ticket.status == "open")
        )).scalars().all())
        pending_application_count = len((await session.execute(
            select(Application).where(Application.status == "pending")
        )).scalars().all())
        dashboard_user_count = len((await session.execute(select(DashboardUser))).scalars().all())
        return {
            "guild_count": guild_count,
            "total_members": total_members,
            "punishment_count": punishment_count,
            "open_ticket_count": open_ticket_count,
            "pending_application_count": pending_application_count,
            "dashboard_user_count": dashboard_user_count,
        }


async def update_admin_password(admin_id: int, new_password_hash: str) -> None:
    async with get_session() as session:
        admin = await session.get(AdminUser, admin_id)
        if admin:
            admin.password_hash = new_password_hash
            await session.commit()


async def delete_admin_user(admin_id: int) -> bool:
    async with get_session() as session:
        admin = await session.get(AdminUser, admin_id)
        if admin is None or admin.is_superadmin:
            return False  # Superadmins können hierüber nicht gelöscht werden (Schutz vor Aussperrung)
        await session.delete(admin)
        await session.commit()
        return True


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


# ---------- Level-System ----------

XP_PER_LEVEL = 100  # einfache, vorhersehbare Formel: Level = XP // 100


async def get_level_xp(guild_id: int, user_id: int) -> LevelXP:
    async with get_session() as session:
        stmt = select(LevelXP).where(LevelXP.guild_id == guild_id, LevelXP.user_id == user_id)
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()
        if entry is None:
            entry = LevelXP(guild_id=guild_id, user_id=user_id)
            session.add(entry)
            await session.commit()
            await session.refresh(entry)
        return entry


async def add_xp(guild_id: int, user_id: int, amount: int, cooldown_seconds: int) -> tuple[int, int, int, bool] | None:
    """Vergibt XP, sofern der Cooldown seit der letzten Vergabe abgelaufen ist.
    Gibt (neue_xp, neues_level, altes_level, level_up: bool) zurück, oder None,
    wenn der Cooldown noch aktiv ist (keine XP vergeben). altes_level wird
    zurückgegeben (statt nur einem bool), damit bei einem Mehrfach-Level-Sprung
    (z.B. durch /xp add) ALLE dazwischenliegenden Rang-Rollen vergeben werden
    können, nicht nur die für das neue Level -- vorher wurden übersprungene
    Zwischen-Level-Rollen nie vergeben."""
    async with get_session() as session:
        stmt = select(LevelXP).where(LevelXP.guild_id == guild_id, LevelXP.user_id == user_id)
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()
        now = dt.datetime.utcnow()

        if entry is None:
            entry = LevelXP(guild_id=guild_id, user_id=user_id, xp=0, level=0, last_xp_at=now)
            session.add(entry)
        elif (now - entry.last_xp_at).total_seconds() < cooldown_seconds:
            return None

        old_level = entry.level
        entry.xp += amount
        entry.level = entry.xp // XP_PER_LEVEL
        entry.last_xp_at = now
        await session.commit()
        return entry.xp, entry.level, old_level, entry.level > old_level


async def get_leaderboard(guild_id: int, limit: int = 10) -> list[LevelXP]:
    async with get_session() as session:
        stmt = select(LevelXP).where(LevelXP.guild_id == guild_id).order_by(LevelXP.xp.desc()).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def set_level_xp(guild_id: int, user_id: int, xp: int) -> tuple[int, int]:
    """Setzt die XP eines Users direkt auf einen Wert (admin-Befehl /xp set),
    berechnet das Level neu. Gibt (xp, level) zurück."""
    xp = max(0, xp)
    async with get_session() as session:
        stmt = select(LevelXP).where(LevelXP.guild_id == guild_id, LevelXP.user_id == user_id)
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()
        if entry is None:
            entry = LevelXP(guild_id=guild_id, user_id=user_id)
            session.add(entry)
        entry.xp = xp
        entry.level = xp // XP_PER_LEVEL
        await session.commit()
        return entry.xp, entry.level


async def adjust_level_xp(guild_id: int, user_id: int, delta: int) -> tuple[int, int, int, int]:
    """Addiert (oder mit negativem delta subtrahiert) XP eines Users, ohne den
    Nachrichten-Cooldown zu berühren (admin-Befehle /xp add, /xp remove). Gibt
    (alte_xp, neue_xp, altes_level, neues_level) zurück. XP wird nie negativ."""
    async with get_session() as session:
        stmt = select(LevelXP).where(LevelXP.guild_id == guild_id, LevelXP.user_id == user_id)
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()
        if entry is None:
            entry = LevelXP(guild_id=guild_id, user_id=user_id)
            session.add(entry)
        old_xp, old_level = entry.xp, entry.level
        entry.xp = max(0, entry.xp + delta)
        entry.level = entry.xp // XP_PER_LEVEL
        await session.commit()
        return old_xp, entry.xp, old_level, entry.level


async def reset_level_xp(guild_id: int, user_id: int) -> None:
    async with get_session() as session:
        stmt = select(LevelXP).where(LevelXP.guild_id == guild_id, LevelXP.user_id == user_id)
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()
        if entry is not None:
            entry.xp = 0
            entry.level = 0
            await session.commit()


async def add_level_role_reward(guild_id: int, level: int, role_id: int) -> None:
    async with get_session() as session:
        session.add(LevelRoleReward(guild_id=guild_id, level=level, role_id=role_id))
        await session.commit()


async def get_level_role_rewards(guild_id: int) -> list[LevelRoleReward]:
    async with get_session() as session:
        stmt = select(LevelRoleReward).where(LevelRoleReward.guild_id == guild_id).order_by(
            LevelRoleReward.level.asc()
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def remove_level_role_reward(reward_id: int) -> bool:
    async with get_session() as session:
        reward = await session.get(LevelRoleReward, reward_id)
        if reward is None:
            return False
        await session.delete(reward)
        await session.commit()
        return True


# ---------- Invite-Tracking ----------

async def get_invite_records(guild_id: int) -> dict[str, InviteRecord]:
    async with get_session() as session:
        stmt = select(InviteRecord).where(InviteRecord.guild_id == guild_id)
        result = await session.execute(stmt)
        return {rec.code: rec for rec in result.scalars().all()}


async def upsert_invite_record(guild_id: int, code: str, inviter_id: int, uses: int) -> None:
    async with get_session() as session:
        stmt = select(InviteRecord).where(InviteRecord.code == code)
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if record is None:
            session.add(InviteRecord(guild_id=guild_id, code=code, inviter_id=inviter_id, uses=uses))
        else:
            record.uses = uses
            record.inviter_id = inviter_id
        await session.commit()


async def remove_invite_record(code: str) -> None:
    async with get_session() as session:
        stmt = select(InviteRecord).where(InviteRecord.code == code)
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if record:
            await session.delete(record)
            await session.commit()


async def record_invite_join(guild_id: int, member_id: int, inviter_id: int, is_fake: bool) -> None:
    async with get_session() as session:
        session.add(InviteJoin(
            guild_id=guild_id, member_id=member_id, inviter_id=inviter_id, is_fake=is_fake,
        ))
        await session.commit()


async def get_invite_count(guild_id: int, user_id: int, since: "dt.datetime | None" = None) -> int:
    """Zählt ECHTE (nicht Fake-)Einladungen eines Users. Mit since= nur
    Beitritte NACH diesem Zeitpunkt (für Gewinnspiele mit 'nur neue Invites')."""
    async with get_session() as session:
        stmt = select(InviteJoin).where(
            InviteJoin.guild_id == guild_id, InviteJoin.inviter_id == user_id, InviteJoin.is_fake == False,  # noqa: E712
        )
        if since:
            stmt = stmt.where(InviteJoin.joined_at >= since)
        result = await session.execute(stmt)
        return len(result.scalars().all())


async def get_invite_leaderboard(guild_id: int, limit: int = 10) -> list[tuple[int, int]]:
    """Top-Einlader eines Servers nach ECHTEN (nicht Fake-)Einladungen, absteigend.
    Gibt eine Liste aus (inviter_id, anzahl) zurück."""
    async with get_session() as session:
        stmt = (
            select(InviteJoin.inviter_id, func.count(InviteJoin.id).label("count"))
            .where(InviteJoin.guild_id == guild_id, InviteJoin.is_fake == False)  # noqa: E712
            .group_by(InviteJoin.inviter_id)
            .order_by(func.count(InviteJoin.id).desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]


async def get_invite_stats(guild_id: int, user_id: int) -> dict:
    """Detaillierte Invite-Statistik eines Users: echte, fake und gesamt Einladungen."""
    async with get_session() as session:
        stmt = select(InviteJoin).where(InviteJoin.guild_id == guild_id, InviteJoin.inviter_id == user_id)
        result = await session.execute(stmt)
        joins = result.scalars().all()
        real = sum(1 for j in joins if not j.is_fake)
        fake = sum(1 for j in joins if j.is_fake)
        return {"real": real, "fake": fake, "total": len(joins)}


# ---------- Giveaway-System ----------

async def create_giveaway(guild_id: int, channel_id: int, name: str, description: str, sponsor: str,
                           invites_required: int, use_new_invites_only: bool, started_by: int,
                           ends_at: "dt.datetime") -> Giveaway:
    async with get_session() as session:
        giveaway = Giveaway(
            guild_id=guild_id, channel_id=channel_id, name=name, description=description, sponsor=sponsor,
            invites_required=invites_required, use_new_invites_only=use_new_invites_only,
            started_by=started_by, ends_at=ends_at,
        )
        session.add(giveaway)
        await session.commit()
        await session.refresh(giveaway)
        return giveaway


async def set_giveaway_message_id(giveaway_id: int, message_id: int) -> None:
    async with get_session() as session:
        giveaway = await session.get(Giveaway, giveaway_id)
        if giveaway:
            giveaway.message_id = message_id
            await session.commit()


async def get_active_giveaways() -> list[Giveaway]:
    async with get_session() as session:
        stmt = select(Giveaway).where(Giveaway.ended == False)  # noqa: E712
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_giveaways_for_guild(guild_id: int) -> list[Giveaway]:
    async with get_session() as session:
        stmt = select(Giveaway).where(Giveaway.guild_id == guild_id).order_by(Giveaway.started_at.desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_giveaway(giveaway_id: int) -> Giveaway | None:
    async with get_session() as session:
        return await session.get(Giveaway, giveaway_id)


async def end_giveaway(giveaway_id: int, winner_id: int) -> None:
    async with get_session() as session:
        giveaway = await session.get(Giveaway, giveaway_id)
        if giveaway:
            giveaway.ended = True
            giveaway.winner_id = winner_id
            await session.commit()


async def has_entered_giveaway(giveaway_id: int, user_id: int) -> bool:
    async with get_session() as session:
        stmt = select(GiveawayEntry).where(
            GiveawayEntry.giveaway_id == giveaway_id, GiveawayEntry.user_id == user_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None


async def add_giveaway_entry(giveaway_id: int, user_id: int) -> bool:
    if await has_entered_giveaway(giveaway_id, user_id):
        return False
    async with get_session() as session:
        session.add(GiveawayEntry(giveaway_id=giveaway_id, user_id=user_id))
        await session.commit()
        return True


async def get_giveaway_entries(giveaway_id: int) -> list[GiveawayEntry]:
    async with get_session() as session:
        stmt = select(GiveawayEntry).where(GiveawayEntry.giveaway_id == giveaway_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())


# ---------- Admin-Panel: Gruppen-Berechtigungssystem ----------

async def create_permission_group(name: str, created_by: int) -> PermissionGroup:
    async with get_session() as session:
        group = PermissionGroup(name=name, created_by=created_by)
        session.add(group)
        await session.commit()
        await session.refresh(group)
        return group


async def get_permission_groups() -> list[PermissionGroup]:
    async with get_session() as session:
        result = await session.execute(select(PermissionGroup))
        return list(result.scalars().all())


async def get_permission_group(group_id: int) -> PermissionGroup | None:
    async with get_session() as session:
        return await session.get(PermissionGroup, group_id)


async def delete_permission_group(group_id: int) -> None:
    async with get_session() as session:
        group = await session.get(PermissionGroup, group_id)
        if group:
            await session.delete(group)
        # Zugehörige Einträge in den beiden Verknüpfungstabellen mit aufräumen
        entries = (await session.execute(
            select(PermissionGroupEntry).where(PermissionGroupEntry.group_id == group_id)
        )).scalars().all()
        for e in entries:
            await session.delete(e)
        memberships = (await session.execute(
            select(AdminUserGroup).where(AdminUserGroup.group_id == group_id)
        )).scalars().all()
        for m in memberships:
            await session.delete(m)
        await session.commit()


async def get_group_permissions(group_id: int) -> set[str]:
    async with get_session() as session:
        stmt = select(PermissionGroupEntry.permission_key).where(PermissionGroupEntry.group_id == group_id)
        result = await session.execute(stmt)
        return set(result.scalars().all())


async def set_group_permissions(group_id: int, permission_keys: list[str]) -> None:
    """Ersetzt ALLE Rechte einer Gruppe durch die übergebene Liste."""
    async with get_session() as session:
        existing = (await session.execute(
            select(PermissionGroupEntry).where(PermissionGroupEntry.group_id == group_id)
        )).scalars().all()
        for e in existing:
            await session.delete(e)
        for key in permission_keys:
            session.add(PermissionGroupEntry(group_id=group_id, permission_key=key))
        await session.commit()


async def assign_admin_to_group(admin_id: int, group_id: int) -> None:
    async with get_session() as session:
        stmt = select(AdminUserGroup).where(
            AdminUserGroup.admin_user_id == admin_id, AdminUserGroup.group_id == group_id,
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing:
            return
        session.add(AdminUserGroup(admin_user_id=admin_id, group_id=group_id))
        await session.commit()


async def remove_admin_from_group(admin_id: int, group_id: int) -> None:
    async with get_session() as session:
        stmt = select(AdminUserGroup).where(
            AdminUserGroup.admin_user_id == admin_id, AdminUserGroup.group_id == group_id,
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing:
            await session.delete(existing)
            await session.commit()


async def get_admin_groups(admin_id: int) -> list[PermissionGroup]:
    async with get_session() as session:
        stmt = select(AdminUserGroup.group_id).where(AdminUserGroup.admin_user_id == admin_id)
        group_ids = (await session.execute(stmt)).scalars().all()
        if not group_ids:
            return []
        result = await session.execute(select(PermissionGroup).where(PermissionGroup.id.in_(group_ids)))
        return list(result.scalars().all())


async def get_group_members(group_id: int) -> list[AdminUser]:
    async with get_session() as session:
        stmt = select(AdminUserGroup.admin_user_id).where(AdminUserGroup.group_id == group_id)
        admin_ids = (await session.execute(stmt)).scalars().all()
        if not admin_ids:
            return []
        result = await session.execute(select(AdminUser).where(AdminUser.id.in_(admin_ids)))
        return list(result.scalars().all())


async def get_effective_admin_permissions(admin_id: int) -> set[str]:
    """Individuelle Rechte UND alle Rechte aller Gruppen, denen der Admin
    angehört, zusammen (Vereinigungsmenge)."""
    individual = await get_admin_permissions(admin_id)
    groups = await get_admin_groups(admin_id)
    combined = set(individual)
    for group in groups:
        combined |= await get_group_permissions(group.id)
    return combined


# ---------- Bewerbungssystem-Erweiterung ----------

async def update_application_question(question_id: int, new_text: str) -> bool:
    async with get_session() as session:
        question = await session.get(ApplicationQuestion, question_id)
        if question is None:
            return False
        question.question_text = new_text
        await session.commit()
        return True


async def set_application_notify_channel(guild_id: int, channel_id: int) -> None:
    async with get_session() as session:
        entry = await session.get(ApplicationNotifyChannel, guild_id)
        if entry is None:
            entry = ApplicationNotifyChannel(guild_id=guild_id, channel_id=channel_id)
            session.add(entry)
        else:
            entry.channel_id = channel_id
        await session.commit()


async def get_application_notify_channel(guild_id: int) -> int:
    async with get_session() as session:
        entry = await session.get(ApplicationNotifyChannel, guild_id)
        return entry.channel_id if entry else 0


async def delete_application(application_id: int) -> bool:
    async with get_session() as session:
        application = await session.get(Application, application_id)
        if application is None:
            return False
        answers = (await session.execute(
            select(ApplicationAnswer).where(ApplicationAnswer.application_id == application_id)
        )).scalars().all()
        for a in answers:
            await session.delete(a)
        await session.delete(application)
        await session.commit()
        return True


async def get_application_stats(guild_id: int) -> dict:
    async with get_session() as session:
        all_apps = (await session.execute(
            select(Application).where(Application.guild_id == guild_id)
        )).scalars().all()
        return {
            "pending": len([a for a in all_apps if a.status == "pending"]),
            "accepted": len([a for a in all_apps if a.status == "accepted"]),
            "rejected": len([a for a in all_apps if a.status == "rejected"]),
            "total": len(all_apps),
        }


# ---------- News (Website-weit, über das Admin-Panel verwaltet) ----------

async def create_news_post(title: str, content: str, admin_id: int) -> NewsPost:
    async with get_session() as session:
        post = NewsPost(title=title, content=content, created_by_admin_id=admin_id)
        session.add(post)
        await session.commit()
        await session.refresh(post)
        return post


async def get_news_posts(published_only: bool = False, limit: int = 50) -> list[NewsPost]:
    async with get_session() as session:
        stmt = select(NewsPost)
        if published_only:
            stmt = stmt.where(NewsPost.published == True)  # noqa: E712
        stmt = stmt.order_by(NewsPost.created_at.desc()).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_news_post(post_id: int) -> NewsPost | None:
    async with get_session() as session:
        return await session.get(NewsPost, post_id)


async def delete_news_post(post_id: int) -> bool:
    async with get_session() as session:
        post = await session.get(NewsPost, post_id)
        if post is None:
            return False
        await session.delete(post)
        await session.commit()
        return True


async def set_news_published(post_id: int, published: bool) -> None:
    async with get_session() as session:
        post = await session.get(NewsPost, post_id)
        if post:
            post.published = published
            await session.commit()


# ---------- Werbung/Partner-System ----------

async def get_ad_channel(guild_id: int) -> int:
    async with get_session() as session:
        cfg = await session.get(AdConfig, guild_id)
        return cfg.channel_id if cfg else 0


async def set_ad_channel(guild_id: int, channel_id: int) -> None:
    async with get_session() as session:
        cfg = await session.get(AdConfig, guild_id)
        if cfg is None:
            cfg = AdConfig(guild_id=guild_id, channel_id=channel_id)
            session.add(cfg)
        else:
            cfg.channel_id = channel_id
        await session.commit()


async def add_partner(guild_id: int, name: str, invite_link: str, added_by: int) -> Partner:
    async with get_session() as session:
        partner = Partner(guild_id=guild_id, name=name, invite_link=invite_link, added_by=added_by)
        session.add(partner)
        await session.commit()
        await session.refresh(partner)
        return partner


async def get_partners(guild_id: int) -> list[Partner]:
    async with get_session() as session:
        stmt = select(Partner).where(Partner.guild_id == guild_id).order_by(Partner.created_at.desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def remove_partner(partner_id: int) -> bool:
    async with get_session() as session:
        partner = await session.get(Partner, partner_id)
        if partner is None:
            return False
        await session.delete(partner)
        await session.commit()
        return True


# ---------- Reaction-Roles ----------

async def add_reaction_role(guild_id: int, message_id: int, channel_id: int, emoji: str, role_id: int) -> ReactionRole:
    async with get_session() as session:
        entry = ReactionRole(guild_id=guild_id, message_id=message_id, channel_id=channel_id,
                              emoji=emoji, role_id=role_id)
        session.add(entry)
        await session.commit()
        await session.refresh(entry)
        return entry


async def get_reaction_roles_for_message(message_id: int) -> list[ReactionRole]:
    async with get_session() as session:
        stmt = select(ReactionRole).where(ReactionRole.message_id == message_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_reaction_roles(guild_id: int) -> list[ReactionRole]:
    async with get_session() as session:
        stmt = select(ReactionRole).where(ReactionRole.guild_id == guild_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def remove_reaction_role(entry_id: int) -> bool:
    async with get_session() as session:
        entry = await session.get(ReactionRole, entry_id)
        if entry is None:
            return False
        await session.delete(entry)
        await session.commit()
        return True


# ---------- Vorschlagssystem ----------

async def get_suggestion_channel(guild_id: int) -> int:
    async with get_session() as session:
        cfg = await session.get(SuggestionConfig, guild_id)
        return cfg.channel_id if cfg else 0


async def set_suggestion_channel(guild_id: int, channel_id: int) -> None:
    async with get_session() as session:
        cfg = await session.get(SuggestionConfig, guild_id)
        if cfg is None:
            cfg = SuggestionConfig(guild_id=guild_id, channel_id=channel_id)
            session.add(cfg)
        else:
            cfg.channel_id = channel_id
        await session.commit()


async def create_suggestion(guild_id: int, user_id: int, content: str) -> Suggestion:
    async with get_session() as session:
        suggestion = Suggestion(guild_id=guild_id, user_id=user_id, content=content)
        session.add(suggestion)
        await session.commit()
        await session.refresh(suggestion)
        return suggestion


async def set_suggestion_message_id(suggestion_id: int, message_id: int) -> None:
    async with get_session() as session:
        suggestion = await session.get(Suggestion, suggestion_id)
        if suggestion:
            suggestion.message_id = message_id
            await session.commit()


async def update_suggestion_status(suggestion_id: int, status: str) -> Suggestion | None:
    async with get_session() as session:
        suggestion = await session.get(Suggestion, suggestion_id)
        if suggestion is None:
            return None
        suggestion.status = status
        await session.commit()
        await session.refresh(suggestion)
        return suggestion


async def get_suggestions(guild_id: int, status: str | None = None) -> list[Suggestion]:
    async with get_session() as session:
        stmt = select(Suggestion).where(Suggestion.guild_id == guild_id)
        if status:
            stmt = stmt.where(Suggestion.status == status)
        stmt = stmt.order_by(Suggestion.created_at.desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())


# ---------- Geburtstags-System ----------

async def get_birthday_channel(guild_id: int) -> int:
    async with get_session() as session:
        cfg = await session.get(BirthdayConfig, guild_id)
        return cfg.channel_id if cfg else 0


async def set_birthday_channel(guild_id: int, channel_id: int) -> None:
    async with get_session() as session:
        cfg = await session.get(BirthdayConfig, guild_id)
        if cfg is None:
            cfg = BirthdayConfig(guild_id=guild_id, channel_id=channel_id)
            session.add(cfg)
        else:
            cfg.channel_id = channel_id
        await session.commit()


async def set_waiting_room_message(guild_id: int, message: str) -> None:
    async with get_session() as session:
        settings = await get_or_create_guild_settings(session, guild_id)
        settings.waiting_room_message = message
        await session.commit()
    _settings_snapshot_cache.pop(guild_id, None)


async def set_birthday(guild_id: int, user_id: int, day: int, month: int) -> None:
    async with get_session() as session:
        stmt = select(Birthday).where(Birthday.guild_id == guild_id, Birthday.user_id == user_id)
        entry = (await session.execute(stmt)).scalar_one_or_none()
        if entry is None:
            entry = Birthday(guild_id=guild_id, user_id=user_id, day=day, month=month)
            session.add(entry)
        else:
            entry.day = day
            entry.month = month
        await session.commit()


async def get_birthdays_for_guild(guild_id: int) -> list[Birthday]:
    async with get_session() as session:
        stmt = select(Birthday).where(Birthday.guild_id == guild_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_todays_birthdays(day: int, month: int, year: int) -> list[Birthday]:
    """Alle Geburtstage heute, die dieses Jahr noch nicht gefeiert wurden."""
    async with get_session() as session:
        stmt = select(Birthday).where(
            Birthday.day == day, Birthday.month == month, Birthday.last_announced_year != year,
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def mark_birthday_announced(birthday_id: int, year: int) -> None:
    async with get_session() as session:
        entry = await session.get(Birthday, birthday_id)
        if entry:
            entry.last_announced_year = year
            await session.commit()


# ---------- Economy-System ----------

async def get_balance(guild_id: int, user_id: int) -> EconomyBalance:
    async with get_session() as session:
        stmt = select(EconomyBalance).where(
            EconomyBalance.guild_id == guild_id, EconomyBalance.user_id == user_id,
        )
        entry = (await session.execute(stmt)).scalar_one_or_none()
        if entry is None:
            entry = EconomyBalance(guild_id=guild_id, user_id=user_id, balance=0)
            session.add(entry)
            await session.commit()
            await session.refresh(entry)
        return entry


async def add_balance(guild_id: int, user_id: int, amount: int) -> int:
    """Ändert den Kontostand um amount (auch negativ für Abzug). Gibt den neuen
    Kontostand zurück. Verhindert, dass der Kontostand unter 0 fällt."""
    async with get_session() as session:
        stmt = select(EconomyBalance).where(
            EconomyBalance.guild_id == guild_id, EconomyBalance.user_id == user_id,
        )
        entry = (await session.execute(stmt)).scalar_one_or_none()
        if entry is None:
            entry = EconomyBalance(guild_id=guild_id, user_id=user_id, balance=0)
            session.add(entry)
        entry.balance = max(0, entry.balance + amount)
        await session.commit()
        return entry.balance


async def claim_daily(guild_id: int, user_id: int, amount: int, cooldown_hours: int = 24) -> int | None:
    """Gibt den neuen Kontostand zurück, oder None, wenn der Cooldown noch aktiv ist."""
    async with get_session() as session:
        stmt = select(EconomyBalance).where(
            EconomyBalance.guild_id == guild_id, EconomyBalance.user_id == user_id,
        )
        entry = (await session.execute(stmt)).scalar_one_or_none()
        now = dt.datetime.utcnow()
        if entry is None:
            entry = EconomyBalance(guild_id=guild_id, user_id=user_id, balance=0)
            session.add(entry)
        elif entry.last_daily_claim and (now - entry.last_daily_claim).total_seconds() < cooldown_hours * 3600:
            return None

        entry.balance += amount
        entry.last_daily_claim = now
        await session.commit()
        return entry.balance


async def get_economy_leaderboard(guild_id: int, limit: int = 10) -> list[EconomyBalance]:
    async with get_session() as session:
        stmt = select(EconomyBalance).where(EconomyBalance.guild_id == guild_id).order_by(
            EconomyBalance.balance.desc()
        ).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def add_shop_item(guild_id: int, name: str, price: int, role_id: int = 0) -> ShopItem:
    async with get_session() as session:
        item = ShopItem(guild_id=guild_id, name=name, price=price, role_id=role_id)
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return item


async def get_shop_items(guild_id: int) -> list[ShopItem]:
    async with get_session() as session:
        stmt = select(ShopItem).where(ShopItem.guild_id == guild_id).order_by(ShopItem.price.asc())
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_shop_item(item_id: int) -> ShopItem | None:
    async with get_session() as session:
        return await session.get(ShopItem, item_id)


async def remove_shop_item(item_id: int) -> bool:
    async with get_session() as session:
        item = await session.get(ShopItem, item_id)
        if item is None:
            return False
        await session.delete(item)
        await session.commit()
        return True


# ---------- Willkommen / Abschied ----------

async def get_welcome_config(guild_id: int) -> WelcomeConfig:
    async with get_session() as session:
        cfg = await session.get(WelcomeConfig, guild_id)
        if cfg is None:
            cfg = WelcomeConfig(guild_id=guild_id)
            session.add(cfg)
            await session.commit()
            await session.refresh(cfg)
        return cfg


async def set_welcome_config(
    guild_id: int, *, welcome_channel_id: int | None = None, welcome_message: str | None = None,
    leave_channel_id: int | None = None, leave_message: str | None = None,
) -> None:
    async with get_session() as session:
        cfg = await session.get(WelcomeConfig, guild_id)
        if cfg is None:
            cfg = WelcomeConfig(guild_id=guild_id)
            session.add(cfg)
        if welcome_channel_id is not None:
            cfg.welcome_channel_id = welcome_channel_id
        if welcome_message is not None:
            cfg.welcome_message = welcome_message
        if leave_channel_id is not None:
            cfg.leave_channel_id = leave_channel_id
        if leave_message is not None:
            cfg.leave_message = leave_message
        await session.commit()


# ---------- Zeit-Autorole ----------

async def add_timed_autorole(guild_id: int, role_id: int, days_required: int) -> TimedAutorole:
    async with get_session() as session:
        entry = TimedAutorole(guild_id=guild_id, role_id=role_id, days_required=days_required)
        session.add(entry)
        await session.commit()
        await session.refresh(entry)
        return entry


async def get_timed_autoroles(guild_id: int) -> list[TimedAutorole]:
    async with get_session() as session:
        stmt = select(TimedAutorole).where(TimedAutorole.guild_id == guild_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_all_timed_autoroles() -> list[TimedAutorole]:
    """Für die bot-seitige Hintergrundschleife -- alle Server auf einmal."""
    async with get_session() as session:
        result = await session.execute(select(TimedAutorole))
        return list(result.scalars().all())


async def remove_timed_autorole(entry_id: int) -> bool:
    async with get_session() as session:
        entry = await session.get(TimedAutorole, entry_id)
        if entry is None:
            return False
        await session.delete(entry)
        await session.commit()
        return True


# ---------- Verifizierungs-System ----------

async def get_verification_config(guild_id: int) -> VerificationConfig:
    async with get_session() as session:
        cfg = await session.get(VerificationConfig, guild_id)
        if cfg is None:
            cfg = VerificationConfig(guild_id=guild_id)
            session.add(cfg)
            await session.commit()
            await session.refresh(cfg)
        return cfg


async def set_verification_config(
    guild_id: int, *, enabled: bool | None = None, channel_id: int | None = None,
    verified_role_id: int | None = None,
) -> None:
    async with get_session() as session:
        cfg = await session.get(VerificationConfig, guild_id)
        if cfg is None:
            cfg = VerificationConfig(guild_id=guild_id)
            session.add(cfg)
        if enabled is not None:
            cfg.enabled = enabled
        if channel_id is not None:
            cfg.channel_id = channel_id
        if verified_role_id is not None:
            cfg.verified_role_id = verified_role_id
        await session.commit()


# ---------- Umfragen ----------

async def create_poll(guild_id: int, channel_id: int, question: str, options: list[str], created_by: int) -> Poll:
    async with get_session() as session:
        poll = Poll(guild_id=guild_id, channel_id=channel_id, question=question,
                     options_json=_json.dumps(options), created_by=created_by)
        session.add(poll)
        await session.commit()
        await session.refresh(poll)
        return poll


async def set_poll_message_id(poll_id: int, message_id: int) -> None:
    async with get_session() as session:
        poll = await session.get(Poll, poll_id)
        if poll:
            poll.message_id = message_id
            await session.commit()


async def get_poll(poll_id: int) -> Poll | None:
    async with get_session() as session:
        return await session.get(Poll, poll_id)


async def cast_poll_vote(poll_id: int, user_id: int, option_index: int) -> None:
    async with get_session() as session:
        stmt = select(PollVote).where(PollVote.poll_id == poll_id, PollVote.user_id == user_id)
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing:
            existing.option_index = option_index
        else:
            session.add(PollVote(poll_id=poll_id, user_id=user_id, option_index=option_index))
        await session.commit()


async def get_poll_results(poll_id: int) -> dict[int, int]:
    """Gibt {options_index: anzahl_stimmen} zurück."""
    async with get_session() as session:
        stmt = select(PollVote).where(PollVote.poll_id == poll_id)
        votes = (await session.execute(stmt)).scalars().all()
        counts: dict[int, int] = {}
        for v in votes:
            counts[v.option_index] = counts.get(v.option_index, 0) + 1
        return counts


async def close_poll(poll_id: int) -> None:
    async with get_session() as session:
        poll = await session.get(Poll, poll_id)
        if poll:
            poll.closed = True
            await session.commit()


async def get_polls(guild_id: int, limit: int = 20) -> list[Poll]:
    async with get_session() as session:
        stmt = select(Poll).where(Poll.guild_id == guild_id).order_by(Poll.created_at.desc()).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())


# ---------- Sticky Messages ----------

async def set_sticky_message(channel_id: int, guild_id: int, content: str) -> None:
    async with get_session() as session:
        entry = await session.get(StickyMessage, channel_id)
        if entry is None:
            entry = StickyMessage(channel_id=channel_id, guild_id=guild_id, content=content)
            session.add(entry)
        else:
            entry.content = content
        await session.commit()


async def get_sticky_message(channel_id: int) -> StickyMessage | None:
    async with get_session() as session:
        return await session.get(StickyMessage, channel_id)


async def update_sticky_last_message_id(channel_id: int, message_id: int) -> None:
    async with get_session() as session:
        entry = await session.get(StickyMessage, channel_id)
        if entry:
            entry.last_message_id = message_id
            await session.commit()


async def remove_sticky_message(channel_id: int) -> bool:
    async with get_session() as session:
        entry = await session.get(StickyMessage, channel_id)
        if entry is None:
            return False
        await session.delete(entry)
        await session.commit()
        return True


async def get_sticky_messages_for_guild(guild_id: int) -> list[StickyMessage]:
    async with get_session() as session:
        stmt = select(StickyMessage).where(StickyMessage.guild_id == guild_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())


# ---------- Wortfilter ----------

async def add_banned_word(guild_id: int, word: str) -> BannedWord:
    async with get_session() as session:
        entry = BannedWord(guild_id=guild_id, word=word.lower())
        session.add(entry)
        await session.commit()
        await session.refresh(entry)
        return entry


async def get_banned_words(guild_id: int) -> list[BannedWord]:
    async with get_session() as session:
        stmt = select(BannedWord).where(BannedWord.guild_id == guild_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def remove_banned_word(entry_id: int) -> bool:
    async with get_session() as session:
        entry = await session.get(BannedWord, entry_id)
        if entry is None:
            return False
        await session.delete(entry)
        await session.commit()
        return True


# ---------- Voice-Aktivitäts-Tracking ----------

async def get_voice_time(guild_id: int, user_id: int) -> int:
    """Gezielte Abfrage für einen einzelnen User -- effizienter als
    get_voice_leaderboard() mit hohem Limit, wenn nur EIN Wert gebraucht wird."""
    async with get_session() as session:
        stmt = select(VoiceTime).where(VoiceTime.guild_id == guild_id, VoiceTime.user_id == user_id)
        entry = (await session.execute(stmt)).scalar_one_or_none()
        return entry.total_seconds if entry else 0


async def add_voice_time(guild_id: int, user_id: int, seconds: int) -> None:
    async with get_session() as session:
        stmt = select(VoiceTime).where(VoiceTime.guild_id == guild_id, VoiceTime.user_id == user_id)
        entry = (await session.execute(stmt)).scalar_one_or_none()
        if entry is None:
            entry = VoiceTime(guild_id=guild_id, user_id=user_id, total_seconds=seconds)
            session.add(entry)
        else:
            entry.total_seconds += seconds
        await session.commit()


async def get_voice_leaderboard(guild_id: int, limit: int = 10) -> list[VoiceTime]:
    async with get_session() as session:
        stmt = select(VoiceTime).where(VoiceTime.guild_id == guild_id).order_by(
            VoiceTime.total_seconds.desc()
        ).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())


# ---------- Server-Backup (Snapshot) ----------

async def create_server_backup(guild_id: int, snapshot: dict, created_by: int) -> ServerBackup:
    async with get_session() as session:
        backup = ServerBackup(guild_id=guild_id, snapshot_json=_json.dumps(snapshot), created_by=created_by)
        session.add(backup)
        await session.commit()
        await session.refresh(backup)
        return backup


async def get_server_backups(guild_id: int) -> list[ServerBackup]:
    async with get_session() as session:
        stmt = select(ServerBackup).where(ServerBackup.guild_id == guild_id).order_by(
            ServerBackup.created_at.desc()
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_server_backup(backup_id: int) -> ServerBackup | None:
    async with get_session() as session:
        return await session.get(ServerBackup, backup_id)


# ---------- Event-Ankündigungen ----------

async def create_scheduled_event(
    guild_id: int, channel_id: int, title: str, description: str,
    event_time, created_by: int,
) -> ScheduledEvent:
    async with get_session() as session:
        event = ScheduledEvent(guild_id=guild_id, channel_id=channel_id, title=title,
                                description=description, event_time=event_time, created_by=created_by)
        session.add(event)
        await session.commit()
        await session.refresh(event)
        return event


async def get_upcoming_events(guild_id: int) -> list[ScheduledEvent]:
    async with get_session() as session:
        stmt = select(ScheduledEvent).where(
            ScheduledEvent.guild_id == guild_id, ScheduledEvent.announced == False,  # noqa: E712
        ).order_by(ScheduledEvent.event_time.asc())
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_due_events(now) -> list[ScheduledEvent]:
    """Für die bot-seitige Hintergrundschleife -- alle Server auf einmal."""
    async with get_session() as session:
        stmt = select(ScheduledEvent).where(
            ScheduledEvent.event_time <= now, ScheduledEvent.announced == False,  # noqa: E712
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def mark_event_announced(event_id: int) -> None:
    async with get_session() as session:
        event = await session.get(ScheduledEvent, event_id)
        if event:
            event.announced = True
            await session.commit()


async def remove_scheduled_event(event_id: int) -> bool:
    async with get_session() as session:
        event = await session.get(ScheduledEvent, event_id)
        if event is None:
            return False
        await session.delete(event)
        await session.commit()
        return True


# ---------- Audit-Log (Dashboard) ----------

async def log_dashboard_action(guild_id: int, dashboard_user_id: int, dashboard_username: str, action: str) -> None:
    async with get_session() as session:
        entry = DashboardAuditLog(
            guild_id=guild_id, dashboard_user_id=dashboard_user_id,
            dashboard_username=dashboard_username, action=action,
        )
        session.add(entry)
        await session.commit()


async def get_dashboard_audit_log(guild_id: int, limit: int = 50) -> list[DashboardAuditLog]:
    async with get_session() as session:
        stmt = select(DashboardAuditLog).where(DashboardAuditLog.guild_id == guild_id).order_by(
            DashboardAuditLog.created_at.desc()
        ).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())


# ---------- Server-Aktivitätsstatistik ----------

async def increment_daily_activity(guild_id: int, date_str: str, *, messages: int = 0, joins: int = 0) -> None:
    async with get_session() as session:
        stmt = select(DailyActivity).where(DailyActivity.guild_id == guild_id, DailyActivity.date == date_str)
        entry = (await session.execute(stmt)).scalar_one_or_none()
        if entry is None:
            entry = DailyActivity(guild_id=guild_id, date=date_str, message_count=messages, join_count=joins)
            session.add(entry)
        else:
            entry.message_count += messages
            entry.join_count += joins
        await session.commit()


async def get_daily_activity(guild_id: int, days: int = 14) -> list[DailyActivity]:
    async with get_session() as session:
        stmt = select(DailyActivity).where(DailyActivity.guild_id == guild_id).order_by(
            DailyActivity.date.desc()
        ).limit(days)
        result = await session.execute(stmt)
        return list(reversed(result.scalars().all()))


# ---------- Globale Sperrliste ----------

async def add_to_global_blocklist(user_id: int, reason: str, blocked_by: int) -> None:
    async with get_session() as session:
        entry = await session.get(GlobalBlocklist, user_id)
        if entry is None:
            entry = GlobalBlocklist(user_id=user_id, reason=reason, blocked_by=blocked_by)
            session.add(entry)
        else:
            entry.reason = reason
        await session.commit()


async def remove_from_global_blocklist(user_id: int) -> bool:
    async with get_session() as session:
        entry = await session.get(GlobalBlocklist, user_id)
        if entry is None:
            return False
        await session.delete(entry)
        await session.commit()
        return True


async def is_globally_blocked(user_id: int) -> bool:
    async with get_session() as session:
        entry = await session.get(GlobalBlocklist, user_id)
        return entry is not None


async def get_global_blocklist() -> list[GlobalBlocklist]:
    async with get_session() as session:
        result = await session.execute(select(GlobalBlocklist))
        return list(result.scalars().all())


# ---------- Admin-Login-Historie ----------

async def log_admin_login(admin_user_id: int, username: str, success: bool, ip_address: str = "") -> None:
    async with get_session() as session:
        entry = AdminLoginHistory(admin_user_id=admin_user_id, username=username,
                                   success=success, ip_address=ip_address)
        session.add(entry)
        await session.commit()


async def get_admin_login_history(limit: int = 100) -> list[AdminLoginHistory]:
    async with get_session() as session:
        stmt = select(AdminLoginHistory).order_by(AdminLoginHistory.created_at.desc()).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())


# ---------- Admin-2FA (TOTP) ----------

async def set_admin_totp_secret(admin_id: int, secret: str) -> None:
    async with get_session() as session:
        admin = await session.get(AdminUser, admin_id)
        if admin:
            admin.totp_secret = secret
            await session.commit()


async def set_admin_totp_enabled(admin_id: int, enabled: bool) -> None:
    async with get_session() as session:
        admin = await session.get(AdminUser, admin_id)
        if admin:
            admin.totp_enabled = enabled
            await session.commit()


# ---------- Fehlerprotokoll ----------

async def log_error(guild_id: int, command_name: str, error_text: str) -> None:
    async with get_session() as session:
        entry = ErrorLog(guild_id=guild_id, command_name=command_name, error_text=error_text[:4000])
        session.add(entry)
        await session.commit()


async def get_error_logs(limit: int = 100) -> list[ErrorLog]:
    async with get_session() as session:
        stmt = select(ErrorLog).order_by(ErrorLog.created_at.desc()).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())


# ---------- API-Fehlerquote ----------

async def record_api_call(date_str: str, success: bool) -> None:
    async with get_session() as session:
        stmt = select(ApiCallStat).where(ApiCallStat.date == date_str)
        entry = (await session.execute(stmt)).scalar_one_or_none()
        if entry is None:
            entry = ApiCallStat(date=date_str, success_count=1 if success else 0,
                                 failure_count=0 if success else 1)
            session.add(entry)
        else:
            if success:
                entry.success_count += 1
            else:
                entry.failure_count += 1
        await session.commit()


async def get_api_call_stats(days: int = 14) -> list[ApiCallStat]:
    async with get_session() as session:
        stmt = select(ApiCallStat).order_by(ApiCallStat.date.desc()).limit(days)
        result = await session.execute(stmt)
        return list(reversed(result.scalars().all()))


# ---------- Server-Tags ----------

async def add_guild_tag(guild_id: int, tag: str) -> None:
    async with get_session() as session:
        session.add(GuildTag(guild_id=guild_id, tag=tag))
        await session.commit()


async def get_guild_tags(guild_id: int) -> list[GuildTag]:
    async with get_session() as session:
        stmt = select(GuildTag).where(GuildTag.guild_id == guild_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_all_guild_tags() -> list[GuildTag]:
    async with get_session() as session:
        result = await session.execute(select(GuildTag))
        return list(result.scalars().all())


async def remove_guild_tag(tag_id: int) -> bool:
    async with get_session() as session:
        entry = await session.get(GuildTag, tag_id)
        if entry is None:
            return False
        await session.delete(entry)
        await session.commit()
        return True


# ---------- Interne Server-Notizen ----------

async def add_guild_admin_note(guild_id: int, note: str, created_by: int) -> None:
    async with get_session() as session:
        session.add(GuildAdminNote(guild_id=guild_id, note=note, created_by=created_by))
        await session.commit()


async def get_guild_admin_notes(guild_id: int) -> list[GuildAdminNote]:
    async with get_session() as session:
        stmt = select(GuildAdminNote).where(GuildAdminNote.guild_id == guild_id).order_by(
            GuildAdminNote.created_at.desc()
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def delete_guild_admin_note(note_id: int) -> bool:
    async with get_session() as session:
        entry = await session.get(GuildAdminNote, note_id)
        if entry is None:
            return False
        await session.delete(entry)
        await session.commit()
        return True


# ---------- Changelog ----------

async def add_changelog_entry(version: str, description: str) -> None:
    async with get_session() as session:
        session.add(ChangelogEntry(version=version, description=description))
        await session.commit()


async def get_changelog_entries(limit: int = 30) -> list[ChangelogEntry]:
    async with get_session() as session:
        stmt = select(ChangelogEntry).order_by(ChangelogEntry.created_at.desc()).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def delete_changelog_entry(entry_id: int) -> bool:
    async with get_session() as session:
        entry = await session.get(ChangelogEntry, entry_id)
        if entry is None:
            return False
        await session.delete(entry)
        await session.commit()
        return True


# ---------- Feature-Flags ----------

async def set_feature_flag(key: str, enabled: bool) -> None:
    async with get_session() as session:
        flag = await session.get(FeatureFlag, key)
        if flag is None:
            flag = FeatureFlag(key=key, enabled=enabled)
            session.add(flag)
        else:
            flag.enabled = enabled
        await session.commit()


async def get_feature_flags() -> list[FeatureFlag]:
    async with get_session() as session:
        result = await session.execute(select(FeatureFlag))
        return list(result.scalars().all())


async def is_feature_enabled(key: str, default: bool = True) -> bool:
    async with get_session() as session:
        flag = await session.get(FeatureFlag, key)
        return flag.enabled if flag else default


# ---------- Feedback ----------

async def create_feedback(dashboard_user_id: int, username: str, message: str) -> None:
    async with get_session() as session:
        session.add(Feedback(dashboard_user_id=dashboard_user_id, username=username, message=message))
        await session.commit()


async def get_feedback_entries(status: str | None = None) -> list[Feedback]:
    async with get_session() as session:
        stmt = select(Feedback)
        if status:
            stmt = stmt.where(Feedback.status == status)
        stmt = stmt.order_by(Feedback.created_at.desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def update_feedback_status(feedback_id: int, status: str) -> None:
    async with get_session() as session:
        entry = await session.get(Feedback, feedback_id)
        if entry:
            entry.status = status
            await session.commit()


# ---------- Geplanter Wartungsmodus ----------

async def create_scheduled_maintenance(start_time, end_time, reason: str) -> None:
    async with get_session() as session:
        session.add(ScheduledMaintenance(start_time=start_time, end_time=end_time, reason=reason))
        await session.commit()


async def get_scheduled_maintenances() -> list[ScheduledMaintenance]:
    async with get_session() as session:
        stmt = select(ScheduledMaintenance).where(ScheduledMaintenance.reverted == False)  # noqa: E712
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_due_maintenance_starts(now) -> list[ScheduledMaintenance]:
    async with get_session() as session:
        stmt = select(ScheduledMaintenance).where(
            ScheduledMaintenance.start_time <= now, ScheduledMaintenance.applied == False,  # noqa: E712
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_due_maintenance_ends(now) -> list[ScheduledMaintenance]:
    async with get_session() as session:
        stmt = select(ScheduledMaintenance).where(
            ScheduledMaintenance.end_time <= now, ScheduledMaintenance.applied == True,  # noqa: E712
            ScheduledMaintenance.reverted == False,  # noqa: E712
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def mark_maintenance_applied(entry_id: int) -> None:
    async with get_session() as session:
        entry = await session.get(ScheduledMaintenance, entry_id)
        if entry:
            entry.applied = True
            await session.commit()


async def mark_maintenance_reverted(entry_id: int) -> None:
    async with get_session() as session:
        entry = await session.get(ScheduledMaintenance, entry_id)
        if entry:
            entry.reverted = True
            await session.commit()


# ---------- Rollen-Vorlagen ----------

async def create_role_template(name: str, roles: list[dict], created_by: int) -> RoleTemplate:
    import json as _json_rt
    async with get_session() as session:
        template = RoleTemplate(name=name, roles_json=_json_rt.dumps(roles), created_by=created_by)
        session.add(template)
        await session.commit()
        await session.refresh(template)
        return template


async def get_role_templates() -> list[RoleTemplate]:
    async with get_session() as session:
        result = await session.execute(select(RoleTemplate))
        return list(result.scalars().all())


async def get_role_template(template_id: int) -> RoleTemplate | None:
    async with get_session() as session:
        return await session.get(RoleTemplate, template_id)


async def delete_role_template(template_id: int) -> bool:
    async with get_session() as session:
        entry = await session.get(RoleTemplate, template_id)
        if entry is None:
            return False
        await session.delete(entry)
        await session.commit()
        return True


# ---------- Backup-Gesamtübersicht (alle Server) ----------

async def get_all_server_backups() -> list[ServerBackup]:
    async with get_session() as session:
        stmt = select(ServerBackup).order_by(ServerBackup.created_at.desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())


# ---------- Ticket-Panels (neu, vereinfacht) ----------

async def create_ticket_panel(guild_id: int, name: str, description: str, color: str,
                               category_id: int, created_by: int) -> TicketPanel:
    async with get_session() as session:
        panel = TicketPanel(guild_id=guild_id, name=name, description=description,
                             color=color, category_id=category_id, created_by=created_by)
        session.add(panel)
        await session.commit()
        await session.refresh(panel)
        return panel


async def get_ticket_panels(guild_id: int) -> list[TicketPanel]:
    async with get_session() as session:
        stmt = select(TicketPanel).where(TicketPanel.guild_id == guild_id).order_by(TicketPanel.created_at.desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_ticket_panel(panel_id: int) -> TicketPanel | None:
    async with get_session() as session:
        return await session.get(TicketPanel, panel_id)


async def delete_ticket_panel(panel_id: int) -> bool:
    async with get_session() as session:
        panel = await session.get(TicketPanel, panel_id)
        if panel is None:
            return False
        await session.delete(panel)
        await session.commit()
        return True
