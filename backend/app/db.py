import logging

from sqlalchemy import String, create_engine, event, inspect as sa_inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

log = logging.getLogger("aimva.db")
IS_SQLITE = settings.database_url.startswith("sqlite")

if IS_SQLITE:
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _sqlite_foreign_keys(dbapi_conn, _record):
        # SQLite ignores ON DELETE CASCADE / SET NULL unless this is enabled per connection.
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
else:
    # pre_ping drops connections the database (or a proxy) closed while idle; recycle stays under common idle timeouts.
    engine = create_engine(settings.database_url, pool_pre_ping=True, pool_recycle=1800,
                           pool_size=settings.db_pool_size, max_overflow=settings.db_max_overflow)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(Session, "before_flush")
def _fit_strings(session, _ctx, _instances) -> None:
    """Shorten text that is longer than its column before it reaches the database.

    SQLite ignores VARCHAR lengths, Postgres rejects the whole write, so an AI-written title or note one character
    too long would turn into a 500 in production only. Keys (primary, unique) are left alone: those must fail loudly."""
    for obj in list(session.new) + list(session.dirty):
        mapper = sa_inspect(obj).mapper
        for col in mapper.columns:
            length = getattr(col.type, "length", None)
            if not length or not isinstance(col.type, String) or col.primary_key or col.unique:
                continue
            key = mapper.get_property_by_column(col).key
            value = obj.__dict__.get(key)
            if isinstance(value, str) and len(value) > length:
                log.warning("Shortened %s.%s from %d to %d characters", mapper.class_.__name__, key, len(value), length)
                setattr(obj, key, value[: length - 1] + "\u2026")


class Base(DeclarativeBase):
    pass


def add_missing_columns(conn=None) -> None:
    """Add columns that exist on models but not yet in the database. Only used once, to bring a database created
    before Alembic up to the baseline schema; every later change is an Alembic migration (see migrate())."""
    from sqlalchemy import inspect, text

    if conn is None:
        with engine.begin() as conn:
            return add_missing_columns(conn)
    insp = inspect(conn)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing:
                continue
            default = col.default.arg if col.default is not None and not callable(col.default.arg) else None
            ddl = f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(engine.dialect)}'
            if default is not None:
                ddl += f" DEFAULT {int(default) if isinstance(default, bool) else repr(default)}"
            conn.execute(text(ddl))


def migrate() -> None:
    """Bring the database to the latest schema with Alembic (backend/migrations).

    A database created before migrations existed has tables but no alembic_version: it is topped up to the baseline
    (new tables and columns only, nothing dropped) and stamped, so from then on upgrades run normally."""
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    from . import models  # noqa: F401  (registers every table)

    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    with engine.begin() as conn:
        if not IS_SQLITE:
            # Several workers or containers start at once: one migrates, the rest wait here, then find nothing to do.
            conn.exec_driver_sql("SELECT pg_advisory_xact_lock(727274)")
        cfg.attributes["connection"] = conn
        tables = set(inspect(conn).get_table_names())
        if tables and "alembic_version" not in tables:
            Base.metadata.create_all(conn)
            add_missing_columns(conn)
            command.stamp(cfg, "head")
        else:
            command.upgrade(cfg, "head")


def check_database() -> None:
    """Raise if the database can't answer a trivial query (used by the readiness check)."""
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
