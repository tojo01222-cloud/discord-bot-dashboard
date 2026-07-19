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
    GuildSettings, Punishment, TeamRank, TeamMember, TrustedUser, DashboardUser, BotGuild,
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

async def is_trusted_user(guild_id: int, user_id: int) -> bool:
    async with get_session() as session:
        stmt = select(TrustedUser).where(TrustedUser.guild_id == guild_id, TrustedUser.user_id == user_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None


async def add_trusted_user(guild_id: int, user_id: int, added_by: int) -> bool:
    if await is_trusted_user(guild_id, user_id):
        return False
    async with get_session() as session:
        session.add(TrustedUser(guild_id=guild_id, user_id=user_id, added_by=added_by))
        await session.commit()
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


async def set_anti_spam_enabled(guild_id: int, enabled: bool) -> None:
    async with get_session() as session:
        settings = await get_or_create_guild_settings(session, guild_id)
        settings.anti_spam_enabled = enabled
        await session.commit()


async def get_security_settings(guild_id: int) -> tuple[bool, bool]:
    """Gibt (anti_nuke_enabled, anti_spam_enabled) zurück."""
    async with get_session() as session:
        settings = await get_or_create_guild_settings(session, guild_id)
        return settings.anti_nuke_enabled, settings.anti_spam_enabled


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
