from datetime import datetime, timezone

from app.extensions import db


def _now():
    return datetime.now(timezone.utc)


def _iso(value):
    return value.isoformat() if value else None


class CheckTask(db.Model):
    """A request for a staff member to physically count a product on the shelf."""

    __tablename__ = "check_tasks"

    REASONS = {
        "OUT_OF_STOCK": "System shows zero stock",
        "LOW_STOCK": "Stock at or below reorder level",
        "DISCREPANCY": "Last count did not match the system",
        "OVERDUE_COUNT": "Not counted within its count cycle",
        "NEVER_COUNTED": "Never physically counted",
        "MANUAL": "Requested by a manager",
    }

    STATUSES = ("OPEN", "IN_PROGRESS", "DONE", "CANCELLED")
    PRIORITIES = ("HIGH", "MEDIUM", "LOW")

    id = db.Column(db.Integer, primary_key=True)

    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    completed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    verification_id = db.Column(db.Integer, db.ForeignKey("stock_verifications.id"), nullable=True)

    reason = db.Column(db.String(30), nullable=False)
    priority = db.Column(db.String(10), nullable=False, default="MEDIUM")
    status = db.Column(db.String(20), nullable=False, default="OPEN", index=True)
    note = db.Column(db.Text, nullable=True)
    result_status = db.Column(db.String(30), nullable=True)

    due_at = db.Column(db.DateTime(timezone=True), nullable=True)
    overdue_notified = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=_now, index=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    product = db.relationship("Product", lazy="joined")
    assignee = db.relationship("User", foreign_keys=[assigned_to], lazy="joined")
    creator = db.relationship("User", foreign_keys=[created_by], lazy="joined")
    completer = db.relationship("User", foreign_keys=[completed_by], lazy="joined")

    __table_args__ = (
        db.CheckConstraint("status IN ('OPEN', 'IN_PROGRESS', 'DONE', 'CANCELLED')", name="check_task_status"),
        db.CheckConstraint("priority IN ('HIGH', 'MEDIUM', 'LOW')", name="check_task_priority"),
    )

    @property
    def is_open(self):
        return self.status in ("OPEN", "IN_PROGRESS")

    @property
    def is_overdue(self):
        if not self.is_open or not self.due_at:
            return False
        due = self.due_at if self.due_at.tzinfo else self.due_at.replace(tzinfo=timezone.utc)
        return due < _now()

    def to_dict(self, include_contact=False):
        product = self.product
        assignee = self.assignee
        shelf = product.shelf if product else None
        data = {
            "id": self.id,
            "product_id": self.product_id,
            "product_name": product.name if product else None,
            "sku": product.sku if product else None,
            "barcode": product.barcode if product else None,
            "category": product.category if product else None,
            "system_quantity": product.quantity if product else None,
            "assigned_to": self.assigned_to,
            "assignee": assignee.display_name if assignee else None,
            "shelf_code": shelf.code if shelf else None,
            "shelf_name": shelf.name if shelf else None,
            "created_by": self.creator.display_name if self.creator else "System",
            "completed_by": self.completer.display_name if self.completer else None,
            "reason": self.reason,
            "reason_text": self.REASONS.get(self.reason, self.reason),
            "priority": self.priority,
            "status": self.status,
            "note": self.note,
            "result_status": self.result_status,
            "verification_id": self.verification_id,
            "is_overdue": self.is_overdue,
            "due_at": _iso(self.due_at),
            "created_at": _iso(self.created_at),
            "completed_at": _iso(self.completed_at),
        }

        if include_contact and assignee:
            data["assignee_email"] = assignee.email
            data["assignee_phone"] = assignee.phone

        return data


class Notification(db.Model):

    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    category = db.Column(db.String(30), nullable=False, default="INFO")
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=True)
    link = db.Column(db.String(255), nullable=True)
    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=_now, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "category": self.category,
            "title": self.title,
            "message": self.message,
            "link": self.link,
            "is_read": self.is_read,
            "created_at": _iso(self.created_at),
        }
