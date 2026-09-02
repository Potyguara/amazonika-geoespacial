from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.security import AuditLog


def write_audit(
    db: Session,
    *,
    action: str,
    user_id: UUID | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
            ip_address=ip_address,
            user_agent=(user_agent or "")[:500] or None,
        )
    )
