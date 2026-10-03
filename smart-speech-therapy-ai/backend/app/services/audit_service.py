"""
Audit logging helper (spec section 67): records security-sensitive events.
Call sites decide what counts as sensitive; this just standardizes the write.
"""
import json

from sqlalchemy.orm import Session

from app.models.auth import AuditLog


def log_event(
    db: Session,
    action: str,
    user_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        metadata_json=json.dumps(metadata) if metadata is not None else None,
    )
    db.add(entry)
    db.commit()
