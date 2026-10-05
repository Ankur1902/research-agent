"""Support bounded document text beyond MySQL TEXT's 64 KB ceiling."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import LONGTEXT

revision = "0002"
down_revision = "0001"


def upgrade():
    if op.get_bind().dialect.name == "mysql":
        op.alter_column("documents", "text", existing_type=sa.Text(), type_=LONGTEXT(), existing_nullable=False)


def downgrade():
    # Refuse a lossy downgrade when any stored document exceeds TEXT capacity.
    if op.get_bind().dialect.name == "mysql":
        count = (
            op.get_bind().execute(sa.text("SELECT COUNT(*) FROM documents WHERE OCTET_LENGTH(text) > 65535")).scalar()
        )
        if count:
            raise RuntimeError("Cannot downgrade: a document exceeds MySQL TEXT capacity")
        op.alter_column("documents", "text", existing_type=LONGTEXT(), type_=sa.Text(), existing_nullable=False)
