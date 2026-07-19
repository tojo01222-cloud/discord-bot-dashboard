# All-in-One Discord Bot — Projektplan

## 1. Tech-Stack (final)

| Bereich | Wahl |
|---|---|
| Bot | Python 3.12, `discord.py` (2.x, Slash + Prefix Commands hybrid) |
| Musik | `discord.py` Voice + `yt-dlp` + `FFmpeg` |
| Datenbank | PostgreSQL (racehost.eu unterstützt i.d.R. MySQL/PostgreSQL – muss geprüft werden; Fallback SQLite für den Start) |
| Web-Dashboard | FastAPI (Backend) + Jinja2 oder React-Frontend, Discord OAuth2 Login |
| Admin-Panel | eigener geschützter Bereich innerhalb des Dashboards, Rollen-/Rechteverwaltung pro User |
| Bewerbungs-Webseite | Teil des Dashboards, eigenes Modul mit Formular-Builder |
| KI-Anbindung | Anthropic/OpenAI API (keine eigene KI "from scratch" — das ist technisch nicht sinnvoll machbar) |
| Hosting | racehost.eu (Bot-Prozess), Dashboard ggf. separat (Web-Hosting-Paket oder VPS-Anteil nötig — bitte bei racehost.eu klären, ob Python-Webprozesse dauerhaft laufen dürfen) |
| Prozessverwaltung | `systemd` oder racehost-eigenes Bot-Panel, Auto-Restart bei Crash |

**Wichtiger Hinweis zu racehost.eu:** Reine "Bot-Hosting"-Pakete erlauben oft nur den Discord-Bot-Prozess, nicht zusätzlich einen dauerhaft laufenden Webserver für das Dashboard. Das muss vor Phase 4 geklärt werden (ggf. separates Webhosting/VPS für das Dashboard nötig).

## 2. Architektur / Ordnerstruktur

```
discord-bot/
├── bot/
│   ├── main.py                 # Einstiegspunkt, lädt alle Cogs
│   ├── config.py                # Lädt .env (Token, DB-URL, API-Keys)
│   ├── database/
│   │   ├── models.py             # DB-Schema (SQLAlchemy)
│   │   └── db.py
│   ├── cogs/
│   │   ├── moderation.py          # kick, ban, timeout, warn, mute...
│   │   ├── team_management.py     # uprank, downrank, teamkick, teamliste
│   │   ├── anti_nuke.py
│   │   ├── anti_spam.py
│   │   ├── werbung.py              # Werbe-Kanäle, Partner-System
│   │   ├── strafverzeichnis.py     # Bestrafungs-Log/Dashboard-Anbindung
│   │   ├── tickets.py
│   │   ├── warteraum.py            # Voice-Wartezimmer-System
│   │   ├── musik.py
│   │   ├── fun.py
│   │   ├── ankuendigungen.py
│   │   ├── auto_nachrichten.py
│   │   ├── autorole.py
│   │   ├── serverki.py             # KI-Chat-Kanal
│   │   ├── minecraft_roblox.py     # Server-Status-Panels
│   │   ├── livestream_social.py    # Twitch/YouTube-Benachrichtigungen
│   │   ├── info_help.py            # /help, /serverinfo
│   │   └── settings.py             # Sprache, Server-Einstellungen
│   └── utils/
│       ├── permissions.py         # zentrale Rechteprüfung (Owner/Admin/Team)
│       ├── i18n.py                # DE/EN Sprachsystem
│       └── embeds.py              # einheitliches Design für Panels
├── dashboard/
│   ├── backend/                    # FastAPI: OAuth, API-Routen
│   ├── frontend/                   # Web-UI
│   └── admin/                      # eigenes geschütztes Admin-Modul
├── bewerbungen/                    # Formular-Builder + Logs
└── .env                            # Tokens, Passwort-HASHES (nie Klartext!)
```

## 3. Sicherheits-Grundregeln (nicht verhandelbar)

- Bot-Token, DB-Zugang, API-Keys **nur** in `.env`, niemals im Code oder Chat.
- Admin-Panel-Passwort wird **gehasht** (bcrypt) in der DB gespeichert, nie im Klartext.
- Discord-OAuth: nur die nötigsten Scopes anfragen (`identify`, `guilds`), Tokens verschlüsselt speichern.
- Gespeicherte Nutzerdaten (Login-Logs, IDs) → DSGVO-Hinweis auf der Webseite einbauen (Datenschutzerklärung, da EU-Nutzer betroffen sind).
- Rollenbasierte Zugriffskontrolle für Admin-Panel-Bereiche (nicht "ein Passwort für alles", sondern pro Discord-User zuweisbare Berechtigungen).

## 4. Phasenplan (dein gewünschter Ablauf)

**Phase 1 — Planung & Grundgerüst** *(diese Datei + Bot-Skelett)*
- Projektstruktur, DB-Schema, Command-Framework (Slash + Prefix parallel), zentrales Berechtigungssystem, Sprachsystem (DE/EN)

**Phase 2 — Befehle & Kernsysteme**
- Moderation (kick/ban/timeout/warn), Team-Management (uprank/downrank/teamkick/teamliste), Anti-Nuke, Anti-Spam, Strafverzeichnis, Server-Info, Help-System

**Phase 3 — Überarbeitung**
- Testen, Bugfixes, Rechte-Feinschliff, Konsistenz aller Commands (Slash **und** `!`-Prefix identisch)

**Phase 4 — Dashboard (Basis)**
- Discord-OAuth-Login, Server-Auswahl, Basis-Einstellungen speichern

**Phase 5 — Musiksystem**
- Voice-Channel-Bindung, Auto-Rejoin, YouTube-Suche via yt-dlp, `/play`, Genre-Wiedergabe, Werbe-Filter

**Phase 6 — Ticket- & Warteraum-System**
- Professionelle Ticket-Panels (mehrere Designs), Warteraum-Voice-Erkennung mit automatischer Text-Benachrichtigung

**Phase 7 — Bewerbungssystem**
- Formular-Builder, eigene Bewerbungs-Webseite, Log-Ansicht im Dashboard

**Phase 8 — Admin-Panel (Dashboard)**
- Nur für berechtigte User, Team-Gruppen, Rechteverwaltung, Bot start/stop, globale Ankündigungen, Server-Statistiken (50+ Funktionen wie gewünscht)

**Phase 9 — Rest**
- Fun-Commands, Werbung/Partner-System, Social-Media-Benachrichtigungen, Minecraft/Roblox-Status-Panels, Livestream-Benachrichtigungen, Auto-Nachrichten, Server-KI

**Phase 10 — Finaler Feinschliff**
- Alle Commands durchtesten, Performance, Fehlerbehandlung, Dokumentation

## 5. Realistischer Hinweis zur Befehlsanzahl

„350+ Befehle" ist als **Marketing-Zahl** unrealistisch, wenn jeder einzeln sinnvoll und einzigartig sein soll. Realistisch kommen wir bei einem Bot dieses Funktionsumfangs auf **120–180 echte, sinnvolle Commands** — viele Wünsche (z. B. Warnungen anzeigen, Warnung löschen, Warnliste, Warnung bearbeiten) lassen sich sauber in Command-Gruppen bündeln, was besser ist als künstlich aufgeblähte Zahlen. Ich baue das Framework aber so, dass jederzeit einfach weitere Commands ergänzt werden können.

## 6. Offene Entscheidungen für Phase 1

1. Datenbank: SQLite zum Start (einfach, kein Setup) oder direkt PostgreSQL/MySQL auf racehost.eu?
2. Soll ich mit dem Bot-Grundgerüst (Cog-Loader, Berechtigungssystem, DE/EN-System) jetzt direkt beginnen?
