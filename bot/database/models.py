"""
Datenbank-Schema (SQLAlchemy, async-fähig).
Start mit SQLite — später ohne Codeänderung auf MySQL/PostgreSQL umstellbar,
nur DATABASE_URL in .env anpassen.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, String, Boolean, DateTime, ForeignKey, Text, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class GuildSettings(Base):
    """Server-spezifische Grundeinstellungen (pro Discord-Server genau 1 Zeile)."""
    __tablename__ = "guild_settings"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    language: Mapped[str] = mapped_column(String(2), default="de")  # "de" oder "en"

    # Log-/Funktionskanäle (0 = nicht gesetzt)
    mod_log_channel_id: Mapped[int] = mapped_column(BigInteger, default=0)
    punishment_log_channel_id: Mapped[int] = mapped_column(BigInteger, default=0)
    announcement_channel_id: Mapped[int] = mapped_column(BigInteger, default=0)
    ticket_category_id: Mapped[int] = mapped_column(BigInteger, default=0)
    waiting_room_voice_channel_id: Mapped[int] = mapped_column(BigInteger, default=0)
    waiting_room_notify_channel_id: Mapped[int] = mapped_column(BigInteger, default=0)
    music_bound_voice_channel_id: Mapped[int] = mapped_column(BigInteger, default=0)

    # Anti-Nuke / Anti-Spam ein/aus
    anti_nuke_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    anti_spam_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Auto-Role (0 = keine)
    autorole_id: Mapped[int] = mapped_column(BigInteger, default=0)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class TeamRank(Base):
    """Definierte Team-Ränge pro Server, für Uprank/Downrank-System (geordnete Hierarchie)."""
    __tablename__ = "team_ranks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    role_id: Mapped[int] = mapped_column(BigInteger)
    position: Mapped[int] = mapped_column(Integer)  # 0 = niedrigster Rang, aufsteigend


class TeamMember(Base):
    """Team-Mitglieder-Liste (für /teamliste, Uprank/Downrank-Historie)."""
    __tablename__ = "team_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    current_rank_id: Mapped[int | None] = mapped_column(ForeignKey("team_ranks.id"), nullable=True)
    joined_team_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class Punishment(Base):
    """Strafverzeichnis: sowohl normale User-Strafen als auch Team-interne Strafen (Team-Warns)."""
    __tablename__ = "punishments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    moderator_id: Mapped[int] = mapped_column(BigInteger)
    type: Mapped[str] = mapped_column(String(20))  # warn, timeout, kick, ban, team_warn, team_kick, anti_nuke_action, anti_spam_timeout
    reason: Mapped[str] = mapped_column(Text, default="")
    is_team_punishment: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)  # false = gelöscht/aufgehoben


class AdvertisingChannel(Base):
    """Werbe-Kanäle: erlaubt Werbung, verbietet Werbung, oder komplett gesperrt."""
    __tablename__ = "advertising_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    channel_id: Mapped[int] = mapped_column(BigInteger)
    mode: Mapped[str] = mapped_column(String(20))  # "allowed", "forbidden", "locked"


class TrustedUser(Base):
    """Anti-Nuke-Whitelist: diese User lösen die Anti-Nuke-Erkennung nicht aus
    (z.B. weitere vertrauenswürdige Admins/Bots neben dem Server-Owner)."""
    __tablename__ = "trusted_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    added_by: Mapped[int] = mapped_column(BigInteger)
    added_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class DashboardUser(Base):
    """Jeder, der sich einmal über Discord im Web-Dashboard eingeloggt hat.
    Bekommt eine eigene, vom Bot unabhängige ID (wie gewünscht: 'jeder registrierte
    User erhält eine ID'). first_login_at/last_login_at dienen zugleich als
    einfaches Login-Log (wann zuletzt eingeloggt)."""
    __tablename__ = "dashboard_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID4
    discord_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str] = mapped_column(String(100))
    avatar_hash: Mapped[str] = mapped_column(String(64), default="")
    first_login_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    last_login_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class BotGuild(Base):
    """Server, auf denen der Bot aktuell Mitglied ist. Wird vom Bot-Prozess selbst
    gepflegt (on_ready/on_guild_join/on_guild_remove) und vom Dashboard gelesen,
    um zu prüfen, ob der Bot überhaupt auf einem Server ist, den ein Dashboard-User
    verwalten möchte."""
    __tablename__ = "bot_guilds"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    icon_hash: Mapped[str] = mapped_column(String(64), default="")
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
