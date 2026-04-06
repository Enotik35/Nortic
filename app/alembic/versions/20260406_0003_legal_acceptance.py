"""Add legal acceptance fields to users."""

from alembic import op
import sqlalchemy as sa


revision = "20260406_0003"
down_revision = "20260403_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("legal_accepted_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("legal_version", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "legal_version")
    op.drop_column("users", "legal_accepted_at")
