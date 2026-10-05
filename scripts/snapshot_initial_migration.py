"""Development utility: freeze schema operations before the first deployment.

Never run this against a repository with an already deployed initial revision.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
from alembic.autogenerate import produce_migrations, render_python_code  # noqa: E402
from alembic.migration import MigrationContext  # noqa: E402
from app.core.db import Base  # noqa: E402
from app.models import entities  # noqa: E402,F401
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402


def snapshot(connection):
    migration = produce_migrations(MigrationContext.configure(connection), Base.metadata)
    upgrade = render_python_code(migration.upgrade_ops)
    downgrade = render_python_code(migration.downgrade_ops)
    prefix = '"""Initial immutable relational schema."""\nimport sqlalchemy as sa\nfrom alembic import op\n\nrevision = "0001"\ndown_revision = None\n\n'
    path = Path(__file__).resolve().parents[1] / "apps/api/migrations/versions/0001_initial.py"
    path.write_text(
        prefix + "def upgrade():\n" + upgrade + "\n\ndef downgrade():\n" + downgrade + "\n", encoding="utf-8"
    )


async def main():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.connect() as connection:
        await connection.run_sync(snapshot)
    await engine.dispose()


asyncio.run(main())
