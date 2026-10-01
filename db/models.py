from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(256), default="")
    role: Mapped[str] = mapped_column(String(32), default="reviewer")  # viewer|reviewer|admin
    password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    evaluations: Mapped[list[Evaluation]] = relationship(back_populates="owner")


class Library(Base):
    __tablename__ = "libraries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    repo: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256), default="")
    blurb: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    versions: Mapped[list[LibraryVersion]] = relationship(back_populates="library")
    evaluations: Mapped[list[Evaluation]] = relationship(back_populates="library")


class LibraryVersion(Base):
    __tablename__ = "library_versions"
    __table_args__ = (UniqueConstraint("library_id", "ref", name="uq_library_ref"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    library_id: Mapped[str] = mapped_column(ForeignKey("libraries.id"), index=True)
    ref: Mapped[str] = mapped_column(String(256), default="")
    commit_sha: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    library: Mapped[Library] = relationship(back_populates="versions")
    evaluations: Mapped[list[Evaluation]] = relationship(back_populates="library_version")


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    library_id: Mapped[str | None] = mapped_column(
        ForeignKey("libraries.id"), nullable=True, index=True
    )
    library_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("library_versions.id"), nullable=True, index=True
    )
    owner_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    # draft | in_progress | completed | not_recommended
    repo: Mapped[str] = mapped_column(String(256), default="", index=True)
    ref: Mapped[str] = mapped_column(String(256), default="")
    form_json: Mapped[str] = mapped_column(Text, default="{}")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    library: Mapped[Library | None] = relationship(back_populates="evaluations")
    library_version: Mapped[LibraryVersion | None] = relationship(back_populates="evaluations")
    owner: Mapped[User | None] = relationship(back_populates="evaluations")
    events: Mapped[list[EvaluationEvent]] = relationship(back_populates="evaluation")
    artifacts: Mapped[list[Artifact]] = relationship(back_populates="evaluation")


class EvaluationEvent(Base):
    __tablename__ = "evaluation_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    evaluation: Mapped[Evaluation] = relationship(back_populates="events")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id"), index=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    # form | pdf | pdf_draft | log | run_manifest | signed_export
    path: Mapped[str] = mapped_column(String(1024), default="")
    content_type: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    evaluation: Mapped[Evaluation] = relationship(back_populates="artifacts")


class AuditEvent(Base):
    """App-level audit (login, user admin) — krok 13."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
