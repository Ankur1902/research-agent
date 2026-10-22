"""Persist budget reservations without changing existing research rows."""

from alembic import op
from app.models.entities import RunLease, SpendReservation

revision = "0003"
down_revision = "0002"


def upgrade():
    SpendReservation.__table__.create(op.get_bind(), checkfirst=True)
    RunLease.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    RunLease.__table__.drop(op.get_bind(), checkfirst=True)
    SpendReservation.__table__.drop(op.get_bind(), checkfirst=True)
