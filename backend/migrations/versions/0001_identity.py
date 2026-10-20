"""Identidad y sesiones; sin tablas logísticas ni extensiones espaciales."""

import sqlalchemy as sa
from alembic import op

revision = "0001_identity"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA monami")
    op.execute("REVOKE ALL ON SCHEMA monami FROM PUBLIC")
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="monami",
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.CheckConstraint("role IN ('cliente', 'empresa', 'conductor')", name="ck_users_role"),
        sa.ForeignKeyConstraint(["organization_id"], ["monami.organizations.id"]),
        schema="monami",
    )
    op.create_index(
        "ix_monami_users_organization_id", "users", ["organization_id"], schema="monami"
    )
    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("token_hash"),
        sa.ForeignKeyConstraint(["user_id"], ["monami.users.id"], ondelete="CASCADE"),
        schema="monami",
    )
    op.create_index("ix_monami_sessions_user_id", "sessions", ["user_id"], schema="monami")
    op.create_index("ix_monami_sessions_expires_at", "sessions", ["expires_at"], schema="monami")


def downgrade() -> None:
    op.drop_table("sessions", schema="monami")
    op.drop_table("users", schema="monami")
    op.drop_table("organizations", schema="monami")
    op.execute("DROP SCHEMA monami")
