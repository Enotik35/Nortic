"""Initial schema for production Postgres deployment."""

from alembic import op
import sqlalchemy as sa


revision = "20260331_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "friend_discounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("discount_percent", sa.Integer(), nullable=False),
        sa.Column("max_usages", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("comment", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_friend_discounts_telegram_id"), "friend_discounts", ["telegram_id"], unique=False)

    op.create_table(
        "servers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("public_key", sa.String(length=255), nullable=False),
        sa.Column("short_id", sa.String(length=32), nullable=False),
        sa.Column("sni", sa.String(length=255), nullable=False),
        sa.Column("flow", sa.String(length=64), nullable=False),
        sa.Column("security", sa.String(length=32), nullable=False),
        sa.Column("transport", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "tariffs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("price_rub", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("device_limit", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("traffic_limit_gb", sa.Integer(), nullable=True),
        sa.Column("is_trial", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_username", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("trial_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ref_code", sa.String(length=64), nullable=True),
        sa.Column("referred_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["referred_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ref_code"),
        sa.UniqueConstraint("telegram_id"),
    )
    op.create_index(op.f("ix_users_ref_code"), "users", ["ref_code"], unique=True)
    op.create_index(op.f("ix_users_telegram_id"), "users", ["telegram_id"], unique=True)

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("tariff_id", sa.Integer(), nullable=False),
        sa.Column("amount_rub", sa.Integer(), nullable=False),
        sa.Column("discount_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("discount_source", sa.String(length=50), nullable=True),
        sa.Column("friend_discount_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("payment_provider", sa.String(length=100), nullable=True),
        sa.Column("payment_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tariff_id"], ["tariffs.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_orders_user_id"), "orders", ["user_id"], unique=False)

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("subscription_number", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=False),
        sa.Column("access_key_id", sa.Integer(), nullable=True),
        sa.Column("device_limit_snapshot", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subscription_number"),
    )
    op.create_index(op.f("ix_subscriptions_subscription_number"), "subscriptions", ["subscription_number"], unique=True)
    op.create_index(op.f("ix_subscriptions_user_id"), "subscriptions", ["user_id"], unique=False)

    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_devices_subscription_id"), "devices", ["subscription_id"], unique=False)
    op.create_index(op.f("ix_devices_user_id"), "devices", ["user_id"], unique=False)

    op.create_table(
        "access_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key_value", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="free"),
        sa.Column("assigned_user_id", sa.Integer(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("subscription_id", sa.Integer(), nullable=True),
        sa.Column("device_id", sa.Integer(), nullable=True),
        sa.Column("server_id", sa.Integer(), nullable=True),
        sa.Column("uuid", sa.String(length=64), nullable=True),
        sa.Column("external_client_id", sa.String(length=128), nullable=True),
        sa.Column("vless_uri", sa.Text(), nullable=True),
        sa.Column("subscription_url", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["server_id"], ["servers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_value"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index(op.f("ix_access_keys_device_id"), "access_keys", ["device_id"], unique=False)
    op.create_index(op.f("ix_access_keys_external_client_id"), "access_keys", ["external_client_id"], unique=False)
    op.create_index(op.f("ix_access_keys_key_value"), "access_keys", ["key_value"], unique=True)
    op.create_index(op.f("ix_access_keys_server_id"), "access_keys", ["server_id"], unique=False)
    op.create_index(op.f("ix_access_keys_subscription_id"), "access_keys", ["subscription_id"], unique=False)
    op.create_index(op.f("ix_access_keys_user_id"), "access_keys", ["user_id"], unique=False)
    op.create_index(op.f("ix_access_keys_uuid"), "access_keys", ["uuid"], unique=True)

    op.create_table(
        "referrals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("referrer_user_id", sa.Integer(), nullable=False),
        sa.Column("referred_user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="registered"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["referred_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["referrer_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("referred_user_id", name="uq_referrals_referred_user_id"),
    )
    op.create_index(op.f("ix_referrals_referred_user_id"), "referrals", ["referred_user_id"], unique=False)
    op.create_index(op.f("ix_referrals_referrer_user_id"), "referrals", ["referrer_user_id"], unique=False)

    op.create_foreign_key(
        "fk_subscriptions_access_key_id_access_keys",
        "subscriptions",
        "access_keys",
        ["access_key_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_subscriptions_access_key_id_access_keys", "subscriptions", type_="foreignkey")
    op.drop_index(op.f("ix_referrals_referrer_user_id"), table_name="referrals")
    op.drop_index(op.f("ix_referrals_referred_user_id"), table_name="referrals")
    op.drop_table("referrals")
    op.drop_index(op.f("ix_access_keys_uuid"), table_name="access_keys")
    op.drop_index(op.f("ix_access_keys_user_id"), table_name="access_keys")
    op.drop_index(op.f("ix_access_keys_subscription_id"), table_name="access_keys")
    op.drop_index(op.f("ix_access_keys_server_id"), table_name="access_keys")
    op.drop_index(op.f("ix_access_keys_key_value"), table_name="access_keys")
    op.drop_index(op.f("ix_access_keys_external_client_id"), table_name="access_keys")
    op.drop_index(op.f("ix_access_keys_device_id"), table_name="access_keys")
    op.drop_table("access_keys")
    op.drop_index(op.f("ix_devices_user_id"), table_name="devices")
    op.drop_index(op.f("ix_devices_subscription_id"), table_name="devices")
    op.drop_table("devices")
    op.drop_index(op.f("ix_subscriptions_user_id"), table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_subscription_number"), table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_index(op.f("ix_orders_user_id"), table_name="orders")
    op.drop_table("orders")
    op.drop_index(op.f("ix_users_telegram_id"), table_name="users")
    op.drop_index(op.f("ix_users_ref_code"), table_name="users")
    op.drop_table("users")
    op.drop_table("tariffs")
    op.drop_table("servers")
    op.drop_index(op.f("ix_friend_discounts_telegram_id"), table_name="friend_discounts")
    op.drop_table("friend_discounts")
