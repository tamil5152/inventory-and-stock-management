
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from app.extensions import db, login_manager


class User(UserMixin, db.Model):

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(
        db.String(80),
        unique=True,
        nullable=False,
        index=True
    )

    email = db.Column(
        db.String(120),
        unique=True,
        nullable=False,
        index=True
    )

    full_name = db.Column(
        db.String(120),
        nullable=True
    )

    phone = db.Column(
        db.String(20),
        nullable=True
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    role = db.Column(
        db.String(20),
        nullable=False,
        default="staff"
    )

    is_active_user = db.Column(
        db.Boolean,
        nullable=False,
        default=True
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    # Relationships

    stock_movements = db.relationship(
        "StockMovement",
        backref="user",
        lazy=True
    )

    audit_logs = db.relationship(
        "AuditLog",
        backref="user",
        lazy=True
    )

    shelves = db.relationship(
        "Shelf",
        secondary="user_shelves",
        back_populates="staff",
        lazy="selectin",
        order_by="Shelf.code"
    )

    @property
    def display_name(self):

        return self.full_name or self.username

    def set_password(self, password):

        if len(password) < 8:
            raise ValueError(
                "Password must contain at least 8 characters."
            )

        self.password_hash = generate_password_hash(password)

    def check_password(self, password):

        return check_password_hash(
            self.password_hash,
            password
        )

    @property
    def is_active(self):

        return self.is_active_user

    def has_role(self, *roles):

        return self.role in roles

    def to_dict(self):

        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "display_name": self.display_name,
            "phone": self.phone,
            "role": self.role,
            "is_active": self.is_active_user,
            "shelves": [
                {"id": s.id, "code": s.code, "name": s.name}
                for s in self.shelves
            ],
            "created_at": (
                self.created_at.isoformat()
                if self.created_at else None
            )
        }

    def __repr__(self):

        return f"<User {self.username}>"


@login_manager.user_loader
def load_user(user_id):

    try:
        return db.session.get(User, int(user_id))

    except (ValueError, TypeError):
        return None
