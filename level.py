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
import logging

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from bot.config import config
from bot.database.models import Base

log = logging.getLogger("bot.database")

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


def _add_missing_columns_sync(conn) -> None:
    """Leichtgewichtige Auto-Migration OHNE Alembic: create_all() legt nur
    fehlende TABELLEN an, aendert aber nie Spalten an bereits existierenden
    Tabellen (siehe Hinweis im Ticket-Modell). Fuer bereits laufende
    Deployments (aeltere DB-Datei/Datenbank) wuerden neu hinzugekommene
    Spalten -- wie Ticket.category_id oder GuildSettings.music_last_genre --
    sonst zu "column does not exist"-Fehlern fuehren. Diese Funktion prueft
    darum bei jedem Start, ob alle im Code definierten Spalten auch wirklich
    in der Datenbank existieren, und ergaenzt fehlende per simplem
    ALTER TABLE ... ADD COLUMN (funktioniert identisch unter SQLite und
    PostgreSQL fuer einfache, nullable/DEFAULT-Spalten wie hier verwendet)."""
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # brandneue Tabelle -- create_all() hat sie bereits vollstaendig angelegt
        existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_columns:
                continue
            col_type = column.type.compile(dialect=conn.dialect)
            default_clause = ""
            if column.default is not None and column.default.is_scalar:
                value = column.default.arg
                if isinstance(value, bool):
                    # WICHTIG: Postgres akzeptiert fuer BOOLEAN-Spalten keine
                    # Ganzzahl-Literale (0/1) als DEFAULT, nur TRUE/FALSE --
                    # anders als SQLite. TRUE/FALSE funktioniert in beiden.
                    default_clause = f" DEFAULT {'TRUE' if value else 'FALSE'}"
                elif isinstance(value, str):
                    default_clause = f" DEFAULT '{value}'"
                elif isinstance(value, (int, float)):
                    default_clause = f" DEFAULT {value}"
            ddl = f"ALTER TABLE {table.name} ADD COLUMN {column.name} {col_type}{default_clause}"
            try:
                conn.execute(text(ddl))
                log.info("Migration: Spalte '%s' zu Tabelle '%s' hinzugefuegt.", column.name, table.name)
            except Exception:
                log.exception("Migration: Konnte Spalte '%s' zu '%s' nicht hinzufuegen", column.name, table.name)


async def init_db() -> None:
    """Erstellt alle Tabellen, falls sie noch nicht existieren, und ergaenzt
    bei bereits existierenden Tabellen fehlende, neu hinzugekommene Spalten
    (siehe _add_missing_columns_sync). Wird beim Start aufgerufen."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns_sync)


def get_session() -> AsyncSession:
    return async_session()
