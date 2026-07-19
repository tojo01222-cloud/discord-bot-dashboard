"""
Async-Datenbankverbindung.

Unterstuetzt SQLite (lokal/Test) und PostgreSQL (z.B. Neon.tech fuer den
produktiven Betrieb, wenn Bot und Dashboard auf getrennter Infrastruktur
laufen und sich eine Datenbank ueber das Netzwerk teilen muessen).

Bei PostgreSQL-URLs wird automatisch SSL aktiviert (Neon verlangt das).
Einfach in der .env eintragen:
  postgresql+asyncpg://user:passwort@host/datenbankname
(OHNE "?sslmode=require" anhaengen -- das uebernimmt dieser Code automatisch,
da asyncpg dieses Query-Format nicht direkt versteht.)
"""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from bot.config import config
from bot.database.models import Base

_connect_args = {}
if config.DATABASE_URL.startswith("postgresql"):
    _connect_args = {"ssl": "require"}

engine = create_async_engine(config.DATABASE_URL, echo=False, connect_args=_connect_args)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Erstellt alle Tabellen, falls sie noch nicht existieren. Wird beim Start aufgerufen."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def get_session() -> AsyncSession:
    return async_session()
