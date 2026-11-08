"""Alembic migrations: a fresh database, a database from before migrations, and models that drift from migrations."""
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

BACKEND = Path(__file__).resolve().parent.parent

SCRIPT = """
import sys
from sqlalchemy import inspect, text
from app.db import engine, migrate
if sys.argv[1] == "legacy":
    with engine.begin() as c:  # an old database: one table, missing columns, no alembic_version
        c.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR(120), email VARCHAR(255), password_hash VARCHAR(255))"))
        c.execute(text("INSERT INTO users (name, email, password_hash) VALUES ('Old', 'old@x.com', 'h')"))
migrate()
migrate()  # running twice is a no-op
insp = inspect(engine)
cols = {c["name"] for c in insp.get_columns("users")}
with engine.connect() as c:
    print(len(insp.get_table_names()), "token_version" in cols, c.execute(text("SELECT version_num FROM alembic_version")).scalar(),
          c.execute(text("SELECT count(*) FROM users")).scalar())
"""


def run(tmp_path, mode):
    env = {"DATABASE_URL": f"sqlite:///{tmp_path}/m.db", "SECRET_KEY": "x" * 40, "PATH": "/usr/bin:/bin",
           "AGENTS_SCHEDULER": "false"}
    out = subprocess.run([sys.executable, "-c", SCRIPT, mode], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout.split()


def test_fresh_database_is_built_by_migrations(tmp_path):
    tables, has_col, version, users = run(tmp_path, "fresh")
    assert int(tables) == 43 and has_col == "True" and version == "0014" and users == "0"  # 42 tables + alembic_version


def test_database_from_before_migrations_is_upgraded_in_place(tmp_path):
    tables, has_col, version, users = run(tmp_path, "legacy")
    assert int(tables) == 43 and has_col == "True" and version == "0014" and users == "1"  # existing data is kept


def test_models_and_migrations_agree():
    """Fails when app/models.py changed without a migration. Fix: alembic revision --autogenerate -m '...'"""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from alembic.config import Config
    from alembic import command
    from app.db import Base

    engine = sa.create_engine("sqlite://")
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == []
