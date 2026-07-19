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

WICHTIG (aus einem echten Fehler gelernt): Neon (und "Serverless"-Postgres
im Allgemeinen) kann Verbindungen nach einer Weile Inaktivitaet von sich aus
schliessen -- v.a. wenn Render (das Dashboard) zwischendurch wegen
Inaktivitaet "eingeschlafen" ist. Ohne pool_pre_ping wuerde SQLAlchemy eine
solche laengst tote Verbindung aus dem Pool trotzdem wiederverwenden und mit
"connection is closed" fehlschlagen. pool_pre_ping=True testet jede
Verbindung mit einem leichten Ping, BEVOR sie benutzt wird, und baut bei
Bedarf automatisch eine neue auf. pool_recycle sorgt zusaetzlich dafuer,
dass Verbindungen gar nicht erst so alt werden, dass Neon sie von sich aus
kappt.
"""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from bot.config import config
from bot.database.models import Base

_connect_args = {}
_extra_engine_kwargs = {}
if config.DATABASE_URL.startswith("postgresql"):
    _connect_args = {"ssl": "require"}
    _extra_engine_kwargs = {
        "pool_pre_ping": True,   # jede Verbindung vor Gebrauch testen, tote automatisch ersetzen
        "pool_recycle": 280,     # Verbindungen nach max. ~4.5 Minuten Leerlauf von selbst erneuern
    }

engine = create_async_engine(
    config.DATABASE_URL, echo=False, connect_args=_connect_args, **_extra_engine_kwargs,
)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Erstellt alle Tabellen, falls sie noch nicht existieren. Wird beim Start aufgerufen."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def get_session() -> AsyncSession:
    return async_session()
