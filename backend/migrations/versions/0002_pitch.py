"""Escenario de pitch persistido y sesiones de acceso; no carga datos."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_pitch"
down_revision = "0001_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pitch_scenarios",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("generation", sa.Uuid(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="monami",
    )
    op.create_table(
        "pitch_sessions",
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("scenario_id", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("token_hash"),
        sa.ForeignKeyConstraint(["scenario_id"], ["monami.pitch_scenarios.id"], ondelete="CASCADE"),
        schema="monami",
    )
    op.create_index(
        "ix_monami_pitch_sessions_scenario_id", "pitch_sessions", ["scenario_id"], schema="monami"
    )
    op.create_index(
        "ix_monami_pitch_sessions_expires_at", "pitch_sessions", ["expires_at"], schema="monami"
    )
    # Estas tablas no se exponen mediante la API de datos de Supabase.
    for table in ("pitch_scenarios", "pitch_sessions"):
        op.execute(f"ALTER TABLE monami.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON monami.{table} FROM PUBLIC")


def downgrade() -> None:
    op.drop_table("pitch_sessions", schema="monami")
    op.drop_table("pitch_scenarios", schema="monami")
