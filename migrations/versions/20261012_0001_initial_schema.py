"""Create the PostgreSQL-compatible Nurtelora schema.

Revision ID: 20261012_0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "20261012_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "facilities",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("state", sa.Text()),
        sa.Column("lga", sa.Text()),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("phone", sa.Text()),
        sa.Column("services", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("opening_hours", sa.Text()),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("last_verified_at", sa.Text()),
        sa.Column("owner", sa.Text()),
        sa.Column("verification_status", sa.Text(), nullable=False, server_default=sa.text("'unverified'")),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("sender_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("consent_status", sa.Text(), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("preferred_language", sa.Text()),
        sa.Column("registration_state", sa.Text(), nullable=False, server_default=sa.text("'new'")),
        sa.Column("facility_id", sa.Text(), sa.ForeignKey("facilities.id", ondelete="SET NULL")),
        sa.Column("reminder_opt_in", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("stopped", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("pending_appointment_at", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_users_facility_id", "users", ["facility_id"])

    op.create_table(
        "consent_records",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("consent_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("notice_version", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_consent_records_user_id", "consent_records", ["user_id"])

    op.create_table(
        "appointments",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("facility_id", sa.Text(), sa.ForeignKey("facilities.id", ondelete="SET NULL")),
        sa.Column("scheduled_at", sa.Text()),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("confirmation_status", sa.Text(), nullable=False),
        sa.Column("owner", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_appointments_user_id", "appointments", ["user_id"])

    op.create_table(
        "knowledge_entries",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("approved_text", sa.Text(), nullable=False),
        sa.Column("source_title", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.Text()),
        sa.Column("reviewer_role", sa.Text()),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("review_due_at", sa.Text()),
        sa.Column("review_status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
    )
    op.create_index("ix_knowledge_entries_language_review", "knowledge_entries", ["language", "review_status", "review_due_at"])

    op.create_table(
        "processed_messages",
        sa.Column("message_id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("message_type", sa.Text(), nullable=False),
        sa.Column("processing_status", sa.Text(), nullable=False),
        sa.Column("error_category", sa.String(64)),
        sa.Column("outbound_message_id", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_processed_messages_user_id", "processed_messages", ["user_id"])

    op.create_table(
        "interaction_events",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("task_type", sa.Text(), nullable=False),
        sa.Column("language", sa.Text()),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column("failure_category", sa.Text()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_interaction_events_session_id", "interaction_events", ["session_id"])

    op.create_table(
        "workflow_states",
        sa.Column("sender_hash", sa.String(64), primary_key=True),
        sa.Column("pending_consent_expires_at", sa.Text()),
        sa.Column("pending_deletion_expires_at", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    raise RuntimeError("The baseline migration is intentionally irreversible to protect application data.")
