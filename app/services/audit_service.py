from typing import Any, Dict, Optional

from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import AuditLog


def record_audit_event(
    *,
    action: str,
    entity: str,
    actor_user_id: Optional[int] = None,
    entity_id: Optional[int] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> bool:
    try:
        entry = AuditLog(
            action=str(action or "").strip().upper(),
            entity=str(entity or "").strip().upper(),
            actor_user_id=actor_user_id,
            entity_id=entity_id,
            meta_json=meta or {},
        )
        db.session.add(entry)
        db.session.commit()
        return True
    except SQLAlchemyError:
        db.session.rollback()
        return False
