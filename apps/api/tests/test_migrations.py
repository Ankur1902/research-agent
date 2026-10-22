"""Apply the shipped migration chain to an isolated local database."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from app.core.db import Base
from sqlalchemy import create_engine, inspect, text


@pytest.mark.parametrize("legacy", [False, True])
def test_upgrade_head_creates_recovery_and_budget_tables(tmp_path, legacy):
    root = Path(__file__).resolve().parents[3]
    database = tmp_path / "migration.sqlite"
    if legacy:
        old = create_engine(f"sqlite:///{database.as_posix()}")
        try:
            tables = [
                table
                for name, table in Base.metadata.tables.items()
                if name not in {"spend_reservations", "research_run_leases"}
            ]
            Base.metadata.create_all(old, tables=tables)
            with old.begin() as connection:
                connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
                connection.execute(text("INSERT INTO alembic_version VALUES ('0002')"))
                connection.execute(
                    Base.metadata.tables["organizations"].insert().values(id="existing", name="Preserved")
                )
        finally:
            old.dispose()
    environment = dict(
        os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{database.as_posix()}", PYTHONPATH=str(root / "apps/api")
    )
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "apps/api/alembic.ini", "upgrade", "head"],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    try:
        assert {"research_jobs", "spend_reservations", "research_run_leases"} <= set(inspect(engine).get_table_names())
        if legacy:
            with engine.connect() as connection:
                assert (
                    connection.execute(text("SELECT name FROM organizations WHERE id = 'existing'")).scalar()
                    == "Preserved"
                )
    finally:
        engine.dispose()
