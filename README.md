# Setup — Phase 1 Grundgerüst

## 1. Installation

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Konfiguration

1. `.env.example` zu `.env` kopieren
2. Bot-Token eintragen (Discord Developer Portal → deine App → Bot → Token)
3. Deine eigene Discord-User-ID bei `BOT_OWNER_ID` eintragen (Rechtsklick auf dein Profil → ID kopieren, Entwicklermodus muss aktiv sein)

## 3. Bot in Discord Developer Portal einrichten

- Privileged Gateway Intents aktivieren: **Server Members Intent**, **Message Content Intent**
- Unter OAuth2 → URL Generator: Scope `bot` + `applications.commands`, Berechtigung `Administrator` (wie gewünscht — der Bot fragt beim Server-Beitritt automatisch Admin-Rechte an)

## 4. Starten

```bash
python -m bot.main
```

Beim ersten Start werden automatisch:
- die SQLite-Datenbank erstellt (`bot_database.db`)
- alle Cogs aus `bot/cogs/` geladen
- alle Slash-Commands zu Discord synchronisiert

## Aktueller Stand (Phase 1 + 2)

✅ Cog-Loader (neue Dateien in `bot/cogs/` werden automatisch erkannt)
✅ Hybrid-Commands (jeder Befehl funktioniert automatisch als `/befehl` UND `!befehl`)
✅ Zentrales Berechtigungssystem (`bot/utils/permissions.py`) — greift jetzt korrekt für Slash UND Prefix
✅ Globaler Fehler-Handler (saubere Meldungen statt Tracebacks bei fehlender Berechtigung/falscher Eingabe)
✅ DE/EN-Sprachsystem (`bot/utils/i18n.py`)
✅ Einheitliches Embed-Design (`bot/utils/embeds.py`)
✅ Datenbank-Grundschema + Hilfsfunktionen (`bot/utils/db_helpers.py`)
✅ Beispiel-Cog: `/help`, `/serverinfo`

### Neu in Phase 2 — Moderation (`bot/cogs/moderation.py`)
- `/kick <member> [reason]` — MODERATOR
- `/ban <member> [reason]` — MODERATOR
- `/unban <user_id>` — MODERATOR
- `/timeout <member> <10m|1h|1d...> [reason]` — MODERATOR
- `/warn add <member> [reason]` — MODERATOR
- `/warn list <member>` — MODERATOR
- `/warn remove <warning_id>` — MODERATOR

Alle Befehle prüfen zusätzlich die Rollen-Hierarchie (man kann niemanden mit gleicher/höherer Rolle moderieren, außer man ist Server-Owner).

### Neu in Phase 2 — Team-Management (`bot/cogs/team_management.py`)
- `/teamrank add <role>` — SERVER_ADMIN — definiert die Rang-Hierarchie
- `/teamrank list` — zeigt alle Ränge
- `/teamrank remove <role>` — SERVER_ADMIN
- `/uprank <member>` — MODERATOR — befördert zum nächsthöheren Team-Rang
- `/downrank <member>` — MODERATOR — stuft zurück
- `/teamkick <member> [reason]` — SERVER_ADMIN — entfernt alle Team-Rollen
- `/teamliste` — zeigt alle Teammitglieder mit aktuellem Rang

**Wichtig:** Bevor Uprank/Downrank funktioniert, muss zuerst mit `/teamrank add` die Rang-Hierarchie eingerichtet werden (niedrigster Rang zuerst hinzufügen).

### Neu — Anti-Nuke (`bot/cogs/anti_nuke.py`)
- Erkennt automatisch verdächtig viele Kanal-Löschungen, Rollen-Löschungen oder Bans in kurzer Zeit (Standard: 3 Aktionen in 10 Sekunden)
- Reagiert automatisch: entfernt alle Rollen des Verursachers, loggt den Vorfall
- `/antinuke on|off` — SERVER_ADMIN
- `/antinuke trust <member>` / `/antinuke untrust <member>` / `/antinuke trustlist` — Whitelist für vertrauenswürdige Admins (Server-Owner ist immer automatisch ausgenommen)
- Meldungen gehen in den Log-Kanal, der über die Datenbank (`mod_log_channel_id`) gesetzt ist — dafür fehlt aktuell noch ein `/setlogchannel`-Befehl (kommt mit den Team-Einrichtungsbefehlen)

### Neu — Anti-Spam (`bot/cogs/anti_spam.py`)
- Erkennt Nachrichten-Spam (Standard: 5 Nachrichten in 6 Sekunden)
- Löscht die Spam-Nachrichten automatisch und setzt den User für 5 Minuten in Timeout
- `/antispam on|off` — SERVER_ADMIN

**Hinweis:** Beide Systeme sind standardmäßig **aktiviert** (siehe Datenbank-Default). Schwellenwerte sind aktuell im Code fest hinterlegt (`THRESHOLD_COUNT`, `THRESHOLD_WINDOW_SECONDS` in den jeweiligen Dateien) — im Dashboard (Phase 8) werden diese pro Server einstellbar.

## Nächster Schritt (Phase 3, Fortsetzung)

Weiterhin: alles bei dir testen, dann Team-Einrichtungsbefehle (Log-Kanäle setzen etc.) und danach laut Plan zum Dashboard.

---

# Phase 4 — Web-Dashboard (Basis)

Das Dashboard ist ein **eigener Prozess** (`dashboard/backend/`), getrennt vom Bot. Beide teilen sich dieselbe `.env` und dieselbe Datenbank, laufen aber unabhängig — wenn das Dashboard abstürzt, läuft der Bot weiter und umgekehrt.

## Was funktioniert

- Login über Discord (OAuth2)
- Jeder eingeloggte User bekommt eine eigene, zufällige Dashboard-ID
- Server-Auswahl (zeigt nur Server, wo der User Admin-Rechte hat)
- Falls der Bot dort noch nicht drauf ist: direkter Einladungs-Link
- Basis-Einstellungen pro Server: Sprache, Moderations-Log-Kanal, Strafverzeichnis-Kanal, Ankündigungs-Kanal (als Dropdown mit den echten Kanälen des Servers)
- Datenschutzerklärung unter `/datenschutz` (Entwurf — vor echtem Betrieb rechtlich prüfen lassen!)

## Setup — Teil 1: Datenbank bei Neon.tech (kostenlos, dauerhaft)

Bot (racehost.eu) und Dashboard (Render) laufen auf getrennten Anbietern und brauchen eine gemeinsame, über das Internet erreichbare Datenbank.

1. [neon.tech](https://neon.tech) → kostenlos registrieren (geht auch mit GitHub-Login)
2. "Create a project" → Namen vergeben (z.B. `discord-bot`) → erstellen
3. Im Projekt-Dashboard: **Connection string** kopieren. Sieht ungefähr so aus:
   `postgresql://user:passwort@ep-xxxxx.eu-central-1.aws.neon.tech/neondb?sslmode=require`
4. Für unsere `.env` daraus machen (SQLAlchemy-Treiber-Präfix ändern, `?sslmode=require` am Ende weglassen — das übernimmt der Code automatisch):
   `postgresql+asyncpg://user:passwort@ep-xxxxx.eu-central-1.aws.neon.tech/neondb`
5. Diesen Wert brauchst du gleich zweimal: einmal in der `.env` auf racehost.eu (Bot), einmal in Render (Dashboard) — beide müssen auf **dieselbe** Datenbank zeigen.

## Setup — Teil 2: Code zu GitHub hochladen (ohne Kommandozeile)

Render braucht ein GitHub-Repository, um den Code zu bekommen. Das geht komplett per Maus im Browser:

1. [github.com](https://github.com) → kostenlos registrieren, falls noch nicht vorhanden
2. Oben rechts **+** → **New repository** → Namen vergeben (z.B. `discord-bot-dashboard`) → **Private** auswählen (wichtig, da eure `.env`-Beispieldatei sichtbar wäre, auch wenn sie keine echten Geheimnisse enthält) → **Create repository**
3. Auf der neuen, leeren Repo-Seite: **"uploading an existing file"** anklicken
4. Den kompletten Inhalt des ZIP-Ordners (entpackt) per Drag & Drop reinziehen — **den ganzen Ordnerinhalt**, nicht die ZIP-Datei selbst
5. Unten **"Commit changes"** klicken

## Setup — Teil 3: Discord Developer Portal — OAuth einrichten

1. [discord.com/developers/applications](https://discord.com/developers/applications) → deine Bot-App öffnen
2. Links **OAuth2** → bei **Redirects** hinzufügen (die genaue Render-URL kommt erst in Teil 4 — kannst du auch nachträglich ergänzen): `https://DEIN-APP-NAME.onrender.com/auth/callback`
3. **Client ID** kopieren, **Client Secret** per "Reset Secret" erzeugen und kopieren

## Setup — Teil 4: Render — Dashboard deployen

1. [render.com](https://render.com) → kostenlos registrieren (am einfachsten: "Sign up with GitHub", verbindet direkt)
2. **New +** → **Blueprint**
3. Das gerade hochgeladene GitHub-Repo auswählen → Render erkennt automatisch die Datei `render.yaml` im Projekt und schlägt Build-/Start-Befehl selbst vor
4. Render fragt jetzt nach den Umgebungsvariablen (alles, was `sync: false` in `render.yaml` hat) — hier einfüllen:
   ```
   DISCORD_TOKEN=<dein Bot-Token>
   DISCORD_CLIENT_ID=<aus Teil 3>
   DISCORD_CLIENT_SECRET=<aus Teil 3>
   DISCORD_REDIRECT_URI=https://DEIN-APP-NAME.onrender.com/auth/callback
   DATABASE_URL=<aus Teil 1, im postgresql+asyncpg:// Format>
   BOT_OWNER_ID=<deine Discord User-ID>
   ```
   (`SESSION_SECRET` erzeugt Render automatisch, siehe `render.yaml`)
5. **Apply** / **Create Web Service** klicken — Render baut und startet automatisch
6. Nach ein bis zwei Minuten zeigt Render eine URL wie `https://discord-bot-dashboard-xyz.onrender.com` — das ist dein Dashboard!
7. Falls die tatsächliche URL leicht von dem abweicht, was du in Teil 3 eingetragen hast: im Discord Developer Portal den Redirect korrigieren UND `DISCORD_REDIRECT_URI` in Render unter "Environment" anpassen

## Setup — Teil 5: Bot mit derselben Datenbank verbinden

Auf racehost.eu (Bot-Hosting) in der `.env`-Datei denselben `DATABASE_URL`-Wert aus Teil 1 eintragen (statt der lokalen SQLite-Zeile) und den Bot neu starten. Jetzt teilen sich Bot und Dashboard dieselben Daten.

## Wichtig zu wissen: Gratis-Tier-Verhalten

- **Render Free**: Der Dashboard-Prozess "schläft" nach 15 Minuten ohne Zugriff ein. Der nächste Aufruf danach dauert ca. 30–60 Sekunden (Aufwachen), ist danach aber wieder normal schnell. Für ein Admin-Dashboard, das nicht ständig gebraucht wird, meist unproblematisch.
- **Neon Free**: Bleibt dauerhaft bestehen (im Gegensatz zu Render's eigener Gratis-Datenbank, die sich nach 30 Tagen selbst löscht — deshalb nutzen wir Neon für die Datenbank).

## Bekannter, dokumentierter Kompromiss

Der Login-Session-Token liegt aktuell im signierten (nicht verschlüsselten) Browser-Cookie — üblich für kleinere Dashboards, aber für den produktiven Einsatz mit vielen Nutzern in einer späteren Härtungsphase durch eine serverseitige Session-Ablage zu ersetzen.

## Nächster Schritt (Phase 5)

Musiksystem: Sprachkanal-Bindung, Auto-Rejoin, YouTube-Suche über yt-dlp, `/play`, Genre-Wiedergabe, Werbe-Filter.

---

## Phase 4 — Web-Dashboard (Basis)

Ein separater Prozess (FastAPI), der dieselbe Datenbank wie der Bot nutzt. Enthält:
- Login über Discord-OAuth ("Mit Discord anmelden")
- Übersicht aller Server, auf denen du UND der Bot gemeinsam mit Verwaltungsrechten seid
- Einstellungsseite pro Server: Sprache, Log-Kanäle, Autorole, Anti-Nuke/-Spam an/aus

### Einrichtung

1. Im [Discord Developer Portal](https://discord.com/developers/applications) → deine App → **OAuth2** → General:
   - `DISCORD_CLIENT_ID` und `DISCORD_CLIENT_SECRET` in die `.env` kopieren
   - Unter "Redirects" hinzufügen: `http://localhost:8000/auth/callback` (lokal) bzw. deine echte Dashboard-URL + `/auth/callback` (Produktion) — muss exakt mit `DISCORD_REDIRECT_URI` in der `.env` übereinstimmen
2. Einen zufälligen Session-Secret erzeugen und in `DASHBOARD_SESSION_SECRET` eintragen:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
3. Dashboard starten (Bot muss NICHT gleichzeitig laufen, nutzt aber dieselbe `bot_database.db`):
   ```bash
   uvicorn dashboard.backend.main:app --host 0.0.0.0 --port 8000 --reload
   ```
4. Im Browser `http://localhost:8000` öffnen

### Wichtiger Hinweis zu racehost.eu

Das Bot-Hosting-Egg (Pterodactyl, Python-Yolk) ist für **einen** dauerhaft laufenden Python-Prozess gedacht — den Bot. Das Dashboard ist ein **zweiter, unabhängiger Prozess** (Webserver). Auf racehost.eu brauchst du dafür entweder:
- einen zweiten Server/Slot im Panel (falls das Bot-Hosting-Paket das erlaubt), oder
- ein separates Webhosting-/VPS-Paket

Für lokales Testen reicht `uvicorn ... --reload` auf deinem eigenen Rechner völlig aus.

### Datenschutz-Hinweis

Beim Login werden Discord-Username, Discord-User-ID und Anmeldezeitpunkt gespeichert (Tabellen `dashboard_users`, `login_logs`). Falls das Dashboard öffentlich zugänglich wird, brauchst du dafür eine Datenschutzerklärung (DSGVO, da EU-Nutzer betroffen sind) — das ist noch nicht Teil dieses Codes.

### Noch nicht enthalten (kommt in späteren Phasen)

❌ Admin-Panel (nur für dich mit Passwort) — Phase 8
❌ Musik-Steuerung übers Dashboard — Phase 5
❌ Ticket-/Warteraum-Panel-Designs auswählen — Phase 6
❌ Bewerbungs-Webseite — Phase 7
❌ Kanal-Auswahl per Dropdown (aktuell noch manuelle Kanal-ID-Eingabe) — kommt, sobald der Bot Kanal-Listen für den Dashboard-Prozess bereitstellt

## Nächster Schritt

Testen: Bot UND Dashboard gleichzeitig laufen lassen, einloggen, einen Server auswählen, Einstellungen speichern, prüfen ob der Bot sie tatsächlich nutzt (z.B. `/antinuke`-Meldungen landen im gesetzten Log-Kanal). Danach: Phase 5 — Musiksystem.
