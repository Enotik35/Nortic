"""Add receipt tasks for manual self-employed receipt workflow."""

from alembic import op
import sqlalchemy as sa


revision = "20260424_0006"
down_revision = "20260410_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "receipt_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("payment_id", sa.String(length=255), nullable=True),
        sa.Column("amount_rub", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("source_message_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_receipt_tasks_order_id"), "receipt_tasks", ["order_id"], unique=True)
    op.create_index(op.f("ix_receipt_tasks_user_id"), "receipt_tasks", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_receipt_tasks_user_id"), table_name="receipt_tasks")
    op.drop_index(op.f("ix_receipt_tasks_order_id"), table_name="receipt_tasks")
    op.drop_table("receipt_tasks")
