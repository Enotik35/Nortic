"""Add per-server 3x-ui panel settings for multi-server subscriptions."""

from alembic import op
import sqlalchemy as sa


revision = "20260410_0005"
down_revision = "20260410_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("servers", sa.Column("panel_base_url", sa.String(length=255), nullable=True))
    op.add_column("servers", sa.Column("panel_username", sa.String(length=255), nullable=True))
    op.add_column("servers", sa.Column("panel_password", sa.String(length=255), nullable=True))
    op.add_column("servers", sa.Column("panel_inbound_id", sa.Integer(), nullable=True))
    op.add_column("servers", sa.Column("panel_verify_ssl", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("servers", "panel_verify_ssl")
    op.drop_column("servers", "panel_inbound_id")
    op.drop_column("servers", "panel_password")
    op.drop_column("servers", "panel_username")
    op.drop_column("servers", "panel_base_url")
