from flask import has_request_context, request

from app.extensions import db
from app.models.audit import AuditLog


def log_action(user_id, action, entity_type, entity_id=None, details=None):
    """Add an audit entry to the current session (caller commits)."""

    db.session.add(AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        ip_address=request.remote_addr if has_request_context() else None,
    ))
