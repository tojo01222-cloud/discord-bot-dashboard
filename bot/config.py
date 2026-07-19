"""
Zentrale Konfiguration fuer den BOT-Prozess. Laedt alle Werte aus der .env-Datei.
Niemals Tokens oder Passwoerter hier hart hineinschreiben -- immer ueber
Umgebungsvariablen (.env).

Hinweis: Die OAuth-/Dashboard-spezifischen Werte (DISCORD_CLIENT_ID/SECRET,
SESSION_SECRET) liegen bewusst NICHT hier, sondern in
dashboard/backend/config.py -- Bot und Dashboard sind getrennte Prozesse mit
getrennter, fokussierter Konfiguration, auch wenn beide dieselbe .env lesen.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
    DEFAULT_LANGUAGE: str = os.getenv("DEFAULT_LANGUAGE", "de")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bot_database.db")

    BOT_OWNER_ID: int = int(os.getenv("BOT_OWNER_ID", "0") or "0")

    # Standard-Prefix fuer "!"-Commands (zusaetzlich zu Slash-Commands)
    PREFIX: str = "!"

    @classmethod
    def validate(cls) -> None:
        if not cls.DISCORD_TOKEN:
            raise RuntimeError(
                "DISCORD_TOKEN fehlt! Bitte .env-Datei anlegen (siehe .env.example) "
                "und den Bot-Token dort eintragen."
            )


config = Config()
