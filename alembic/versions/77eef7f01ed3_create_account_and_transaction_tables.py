"""create_account_and_transaction_tables

Revision ID: 77eef7f01ed3
Revises:
Create Date: 2026-10-28 09:37:11.861135

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "77eef7f01ed3"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "accounts",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "balance",
            sa.Numeric(precision=18, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "balance >= 0", name=op.f("ck_accounts_balance_non_negative")
        ),
        sa.CheckConstraint(
            "length(btrim(name)) > 0", name=op.f("ck_accounts_name_not_blank")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounts")),
    )

    op.create_table(
        "transactions",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=10), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("reference_id", sa.String(length=255), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "type IN ('credit', 'debit')",
            name=op.f("ck_transactions_type_valid"),
        ),
        sa.CheckConstraint("amount > 0", name=op.f("ck_transactions_amount_positive")),
        sa.CheckConstraint(
            "length(btrim(description)) > 0",
            name=op.f("ck_transactions_description_not_blank"),
        ),
        sa.CheckConstraint(
            "length(btrim(reference_id)) > 0",
            name=op.f("ck_transactions_reference_id_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_transactions_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transactions")),
        sa.UniqueConstraint(
            "account_id", "reference_id", name="uq_account_reference_id"
        ),
    )

    op.create_index(
        "ix_transactions_account_history",
        "transactions",
        [
            "account_id",
            sa.literal_column("created_at DESC"),
            sa.literal_column("id DESC"),
        ],
        unique=False,
    )

    # Immutability trigger: prevent direct UPDATE or DELETE on transactions
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_transaction_modification()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                RAISE EXCEPTION 'Transactions are immutable: UPDATE not allowed.'
                    USING ERRCODE = 'restrict_violation';
            ELSIF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Transactions are immutable: DELETE not allowed.'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_prevent_transaction_modification
        BEFORE UPDATE OR DELETE ON transactions
        FOR EACH ROW
        EXECUTE FUNCTION prevent_transaction_modification();
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DROP TRIGGER IF EXISTS trg_prevent_transaction_modification ON transactions;"
    )
    op.execute("DROP FUNCTION IF EXISTS prevent_transaction_modification();")
    op.drop_index("ix_transactions_account_history", table_name="transactions")
    op.drop_table("transactions")
    op.drop_table("accounts")
