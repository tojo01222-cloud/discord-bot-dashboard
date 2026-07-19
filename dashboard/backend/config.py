"""
Konfiguration für den Dashboard-Prozess. Läuft als EIGENER Prozess neben dem
Bot (siehe README für den Grund), liest aber dieselbe .env-Datei, damit
Token/Datenbank/OAuth-Daten nur an einer Stelle gepflegt werden müssen.
"""
import os
import secrets

from dotenv import load_dotenv

load_dotenv()


class DashboardConfig:
    DISCORD_CLIENT_ID: str = os.getenv("DISCORD_CLIENT_ID", "")
    DISCORD_CLIENT_SECRET: str = os.getenv("DISCORD_CLIENT_SECRET", "")
    DISCORD_REDIRECT_URI: str = os.getenv("DISCORD_REDIRECT_URI", "")

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bot_database.db")

    # Signiert die Session-Cookies. Falls nicht gesetzt, wird bei jedem Neustart
    # ein neuer Wert erzeugt -> alle User müssten sich neu einloggen. Für den
    # echten Betrieb also SESSION_SECRET fest in die .env eintragen!
    SESSION_SECRET: str = os.getenv("SESSION_SECRET", secrets.token_urlsafe(32))

    DISCORD_API_BASE = "https://discord.com/api/v10"
    OAUTH_SCOPES = "identify guilds"

    @classmethod
    def validate(cls) -> None:
        missing = [name for name in
                   ("DISCORD_CLIENT_ID", "DISCORD_CLIENT_SECRET", "DISCORD_REDIRECT_URI")
                   if not getattr(cls, name)]
        if missing:
            raise RuntimeError(
                f"Fehlende .env-Werte für das Dashboard: {', '.join(missing)}. "
                "Siehe .env.example, Abschnitt 'Discord Application'."
            )


dashboard_config = DashboardConfig()
