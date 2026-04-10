"""Add stable public token for subscription URLs."""

import secrets

from alembic import op
import sqlalchemy as sa


revision = "20260410_0004"
down_revision = "20260406_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("subscription_token", sa.String(length=128), nullable=True))
    op.create_index(
        op.f("ix_subscriptions_subscription_token"),
        "subscriptions",
        ["subscription_token"],
        unique=True,
    )

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id FROM subscriptions WHERE subscription_token IS NULL")).fetchall()
    for row in rows:
        connection.execute(
            sa.text("UPDATE subscriptions SET subscription_token = :token WHERE id = :id"),
            {
                "id": row.id,
                "token": secrets.token_urlsafe(24),
            },
        )

    op.alter_column("subscriptions", "subscription_token", nullable=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_subscriptions_subscription_token"), table_name="subscriptions")
    op.drop_column("subscriptions", "subscription_token")
