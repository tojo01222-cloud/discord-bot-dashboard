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
    language: Mapped[str] = mapped_column(String(2), default="en")  # "de" oder "en" -- Standard beim
    # Bot-Beitritt ist Englisch (siehe Config.DEFAULT_LANGUAGE und get_or_create_guild_settings());
    # diese Spalten-Default ist nur ein Sicherheitsnetz, falls eine Zeile je ohne diesen Weg entsteht.

    # Log-/Funktionskanäle (0 = nicht gesetzt)
    mod_log_channel_id: Mapped[int] = mapped_column(BigInteger, default=0)
    punishment_log_channel_id: Mapped[int] = mapped_column(BigInteger, default=0)
    announcement_channel_id: Mapped[int] = mapped_column(BigInteger, default=0)
    ticket_category_id: Mapped[int] = mapped_column(BigInteger, default=0)
    waiting_room_voice_channel_id: Mapped[int] = mapped_column(BigInteger, default=0)
    waiting_room_notify_channel_id: Mapped[int] = mapped_column(BigInteger, default=0)
    music_bound_voice_channel_id: Mapped[int] = mapped_column(BigInteger, default=0)

    # Zuletzt aktiver Radiosender (Genre-Schlüssel aus RADIO_STREAMS, "" = keiner).
    # Wird bei jedem erfolgreichen /radio gespeichert und beim (Wieder-)Beitritt
    # zum gebundenen Musikkanal automatisch fortgesetzt -- auch nach /stop, einem
    # Kick aus dem Kanal oder einem kompletten Bot-Neustart, siehe musik.py.
    music_last_genre: Mapped[str] = mapped_column(String(30), default="")

    # Anti-Nuke / Anti-Spam ein/aus
    anti_nuke_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    anti_spam_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Anti-Hack (erkennt vermutlich gekaperte Accounts über kanalübergreifenden
    # Spam identischer Inhalte) und Anti-Werbung (löscht unautorisierte Links)
    # -- beide standardmäßig AUS, da sie automatisch Timeouts/Kicks auslösen
    # können und das ausdrücklich pro Server aktiviert werden soll.
    anti_hack_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    anti_werbung_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Auto-Role: "autorole_id" = für normale (menschliche) Mitglieder beim Beitritt,
    # "autorole_bot_id" = für Bot-/App-Accounts beim Beitritt, "autorole_admin_id" =
    # wird automatisch vergeben/entzogen, sobald ein Mitglied Administrator-Rechte
    # bekommt/verliert (auch nachträglich über eine andere Rolle) -- siehe
    # bot/cogs/autorole.py. Alle drei 0 = nicht eingerichtet.
    autorole_id: Mapped[int] = mapped_column(BigInteger, default=0)
    autorole_bot_id: Mapped[int] = mapped_column(BigInteger, default=0)
    autorole_admin_id: Mapped[int] = mapped_column(BigInteger, default=0)

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


class Ticket(Base):
    """Ein Support-Ticket (eigener privater Kanal). Nutzt bewusst die schon
    vorhandenen GuildSettings-Felder (ticket_category_id, mod_log_channel_id
    für das Ticket-Log) statt neue Spalten an einer bestehenden Tabelle zu
    ergänzen -- SQLAlchemys create_all() legt nur fehlende TABELLEN an, ändert
    aber keine Spalten an bereits existierenden Tabellen an (kein
    Migrations-Tool wie Alembic im Einsatz). Eine neue Tabelle ist dagegen
    gefahrlos, auch bei einer schon laufenden Datenbank."""
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    creator_id: Mapped[int] = mapped_column(BigInteger, index=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open, closed
    design: Mapped[str] = mapped_column(String(20), default="standard")
    # Verweist auf TicketCategory.id (0 = kein Ticket-Typ gewählt / altes
    # Einzel-Button-Panel ohne Typen-Auswahl). Bewusst KEIN ForeignKey-Constraint,
    # damit ein späteres Löschen eines Ticket-Typs alte, bereits geschlossene
    # Tickets nicht invalidiert -- die Historie bleibt so immer lesbar.
    category_id: Mapped[int] = mapped_column(Integer, default=0)
    claimed_by: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class TicketCategory(Base):
    """Ein konfigurierbarer Ticket-Typ (z.B. 'Support', 'Bug-Report',
    'Beschwerde', 'Bewerbung'), zwischen denen Nutzer beim Öffnen eines
    Tickets per Auswahlmenü wählen können -- nicht zu verwechseln mit
    GuildSettings.ticket_category_id, das die DISCORD-Kanalkategorie meint,
    in der Ticket-Kanäle standardmäßig entstehen. Jeder Ticket-Typ kann
    optional eine EIGENE Discord-Kanalkategorie haben (channel_category_id),
    z.B. damit Bewerbungs-Tickets in einer anderen Kategorie landen als
    Support-Tickets. 0 = benutzt stattdessen die Standard-Kategorie."""
    __tablename__ = "ticket_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    name: Mapped[str] = mapped_column(String(80))
    emoji: Mapped[str] = mapped_column(String(20), default="🎫")
    description: Mapped[str] = mapped_column(String(150), default="")
    color_hex: Mapped[str] = mapped_column(String(7), default="")  # z.B. "#5865F2", "" = Design-Standardfarbe
    channel_category_id: Mapped[int] = mapped_column(BigInteger, default=0)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class AdminUser(Base):
    """Ein Account fürs Admin-Panel -- eigenes Passwort, KOMPLETT getrennt vom
    normalen Discord-Login der User-Dashboards. Das Passwort wird immer nur
    gehasht gespeichert (siehe dashboard/backend/admin_auth.py), nie im
    Klartext -- auch nicht für andere Admins einsehbar."""
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    last_login_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class AdminPermission(Base):
    """Welcher AdminUser darf welchen Admin-Panel-Bereich nutzen (granulare
    Rechteverwaltung, wie gewünscht). Superadmins (AdminUser.is_superadmin)
    brauchen keine Einträge hier -- die dürfen ohnehin alles."""
    __tablename__ = "admin_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_user_id: Mapped[int] = mapped_column(Integer, index=True)
    permission_key: Mapped[str] = mapped_column(String(50))  # z.B. "servers.view", "broadcast.send"
    granted_by: Mapped[int] = mapped_column(Integer)
    granted_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class GlobalAnnouncement(Base):
    """Log der über das Admin-Panel an alle (oder ausgewählte) Server
    gesendeten Nachrichten -- zur Nachvollziehbarkeit."""
    __tablename__ = "global_announcements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sent_by_admin_id: Mapped[int] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(Text)
    guild_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class BotControlState(Base):
    """Einzige Zeile (id=1), über die das Dashboard dem Bot-Prozess Anweisungen
    gibt (z.B. Wartungsmodus). Der Bot fragt das regelmäßig selbst ab -- ein
    echtes Kill/Restart des Prozesses ist ohne Zugriff auf die
    Hoster-Infrastruktur nicht möglich, siehe README."""
    __tablename__ = "bot_control_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    maintenance_reason: Mapped[str] = mapped_column(String(255), default="")
    updated_by_admin_id: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class ApplicationConfig(Base):
    """Ob und wie das Bewerbungsformular für einen Server aktiv ist. Eigene
    Tabelle statt neuer Spalten an GuildSettings (siehe Hinweis bei Ticket)."""
    __tablename__ = "application_configs"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    welcome_text: Mapped[str] = mapped_column(Text, default="Bewirb dich für unser Team!")


class ApplicationQuestion(Base):
    """Eine konfigurierbare Frage im Bewerbungsformular eines Servers."""
    __tablename__ = "application_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    question_text: Mapped[str] = mapped_column(String(300))
    position: Mapped[int] = mapped_column(Integer, default=0)


class Application(Base):
    """Eine eingereichte Bewerbung."""
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    applicant_discord_id: Mapped[int] = mapped_column(BigInteger, index=True)
    applicant_username: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, accepted, rejected
    submitted_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    reviewed_by: Mapped[int] = mapped_column(BigInteger, default=0)
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class ApplicationAnswer(Base):
    """Eine einzelne Antwort innerhalb einer Bewerbung."""
    __tablename__ = "application_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(Integer, index=True)
    question_text: Mapped[str] = mapped_column(String(300))  # Kopie des Fragetexts zum Zeitpunkt der Bewerbung
    answer_text: Mapped[str] = mapped_column(Text)


# ---------- Phase 9.5: Level-System, Invite-Tracking, Giveaway-System ----------

class LevelXP(Base):
    """XP/Level-Stand eines Users auf einem Server."""
    __tablename__ = "level_xp"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=0)
    last_xp_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class LevelRoleReward(Base):
    """Ab welchem Level welche Rolle automatisch vergeben wird."""
    __tablename__ = "level_role_rewards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    level: Mapped[int] = mapped_column(Integer)
    role_id: Mapped[int] = mapped_column(BigInteger)


class InviteRecord(Base):
    """Bekannter Stand eines Einladungslinks (für den Uses-Vergleich bei
    Beitritten -- Discord liefert keinen direkten 'welcher Link wurde benutzt'
    Event, das muss über den Uses-Unterschied selbst ermittelt werden)."""
    __tablename__ = "invite_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    inviter_id: Mapped[int] = mapped_column(BigInteger, default=0)
    uses: Mapped[int] = mapped_column(Integer, default=0)


class InviteJoin(Base):
    """Wer über wessen Einladung beigetreten ist."""
    __tablename__ = "invite_joins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    member_id: Mapped[int] = mapped_column(BigInteger, index=True)
    inviter_id: Mapped[int] = mapped_column(BigInteger, index=True)
    joined_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    is_fake: Mapped[bool] = mapped_column(Boolean, default=False)  # Account war bei Beitritt <7 Tage alt


class Giveaway(Base):
    """Ein Gewinnspiel."""
    __tablename__ = "giveaways"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    channel_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger, default=0)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    sponsor: Mapped[str] = mapped_column(String(100), default="")
    invites_required: Mapped[int] = mapped_column(Integer, default=0)  # 0 = keine Mindest-Invites nötig
    use_new_invites_only: Mapped[bool] = mapped_column(Boolean, default=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    started_by: Mapped[int] = mapped_column(BigInteger)
    ends_at: Mapped[dt.datetime] = mapped_column(DateTime)
    ended: Mapped[bool] = mapped_column(Boolean, default=False)
    winner_id: Mapped[int] = mapped_column(BigInteger, default=0)


class GiveawayEntry(Base):
    """Eine Teilnahme an einem Gewinnspiel."""
    __tablename__ = "giveaway_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    giveaway_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    entered_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


# ---------- Admin-Panel: Gruppen-Berechtigungssystem ----------

class PermissionGroup(Base):
    """Eine Berechtigungsgruppe (bündelt mehrere permission_key). Admins werden
    Gruppen zugewiesen, statt jedes Recht einzeln pro Person zu vergeben."""
    __tablename__ = "permission_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    created_by: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class PermissionGroupEntry(Base):
    """Ein einzelnes Recht (permission_key) innerhalb einer Gruppe."""
    __tablename__ = "permission_group_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(Integer, index=True)
    permission_key: Mapped[str] = mapped_column(String(50))


class AdminUserGroup(Base):
    """Verknüpfung: welcher AdminUser ist Mitglied welcher PermissionGroup."""
    __tablename__ = "admin_user_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_user_id: Mapped[int] = mapped_column(Integer, index=True)
    group_id: Mapped[int] = mapped_column(Integer, index=True)


# ---------- Bewerbungssystem-Erweiterung ----------

class ApplicationNotifyChannel(Base):
    """In welchem Discord-Kanal neue Bewerbungen gemeldet werden (pro Server)."""
    __tablename__ = "application_notify_channels"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, default=0)


# ---------- Anti-Hack / Anti-Werbung ----------

class AntiExemption(Base):
    """Von einem Anti-System (feature='antihack' oder 'antiwerbung') ausgenommene
    User oder Rollen -- EIN gemeinsames Tabellenschema für beide Systeme (und
    für künftige weitere /anti...-Systeme), damit /..._add und /..._liste
    überall gleich funktionieren."""
    __tablename__ = "anti_exemptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    feature: Mapped[str] = mapped_column(String(20), index=True)  # "antihack" oder "antiwerbung"
    target_type: Mapped[str] = mapped_column(String(10))  # "user" oder "role"
    target_id: Mapped[int] = mapped_column(BigInteger)
    added_by: Mapped[int] = mapped_column(BigInteger)
    added_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class AntiWerbungStrike(Base):
    """Zählt Anti-Werbung-Verstöße pro User für die Eskalationsstufen
    (1. Mal 1h Timeout, 2. Mal 1d, 3. Mal 7d, 4. Mal Kick)."""
    __tablename__ = "anti_werbung_strikes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    last_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class RegisterAccessRole(Base):
    """Rollen, die (zusätzlich zu TEAM/MODERATOR/SERVER_ADMIN) das
    Strafregister (/strafregister) einsehen dürfen -- vergeben ausschließlich
    über /strafregister_recht_geben (SERVER_ADMIN)."""
    __tablename__ = "register_access_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    role_id: Mapped[int] = mapped_column(BigInteger)
    granted_by: Mapped[int] = mapped_column(BigInteger)
    granted_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
