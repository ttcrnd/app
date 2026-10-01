"""Initial schema: users, libraries, evaluations, events, artifacts.

Revision ID: 001_initial
Revises:
Create Date: 2026-09-19
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="reviewer"),
        sa.Column("password_hash", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "libraries",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("repo", sa.String(length=256), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("blurb", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_libraries_repo", "libraries", ["repo"], unique=True)

    op.create_table(
        "library_versions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "library_id", sa.String(length=64), sa.ForeignKey("libraries.id"), nullable=False
        ),
        sa.Column("ref", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("commit_sha", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("library_id", "ref", name="uq_library_ref"),
    )
    op.create_index("ix_library_versions_library_id", "library_versions", ["library_id"])

    op.create_table(
        "evaluations",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("library_id", sa.String(length=64), sa.ForeignKey("libraries.id"), nullable=True),
        sa.Column(
            "library_version_id",
            sa.String(length=64),
            sa.ForeignKey("library_versions.id"),
            nullable=True,
        ),
        sa.Column("owner_user_id", sa.String(length=64), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("repo", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("ref", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("form_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evaluations_library_id", "evaluations", ["library_id"])
    op.create_index("ix_evaluations_library_version_id", "evaluations", ["library_version_id"])
    op.create_index("ix_evaluations_owner_user_id", "evaluations", ["owner_user_id"])
    op.create_index("ix_evaluations_repo", "evaluations", ["repo"])

    op.create_table(
        "evaluation_events",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "evaluation_id", sa.String(length=64), sa.ForeignKey("evaluations.id"), nullable=False
        ),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evaluation_events_evaluation_id", "evaluation_events", ["evaluation_id"])
    op.create_index("ix_evaluation_events_event_type", "evaluation_events", ["event_type"])

    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "evaluation_id", sa.String(length=64), sa.ForeignKey("evaluations.id"), nullable=False
        ),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("content_type", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_artifacts_evaluation_id", "artifacts", ["evaluation_id"])
    op.create_index("ix_artifacts_kind", "artifacts", ["kind"])


def downgrade() -> None:
    op.drop_table("artifacts")
    op.drop_table("evaluation_events")
    op.drop_table("evaluations")
    op.drop_table("library_versions")
    op.drop_table("libraries")
    op.drop_table("users")
