from datetime import datetime, timezone

from app.extensions import db


# Which staff members are responsible for which shelves (many-to-many).
user_shelves = db.Table(
    "user_shelves",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    db.Column("shelf_id", db.Integer, db.ForeignKey("shelves.id", ondelete="CASCADE"), primary_key=True),
)


class Shelf(db.Model):

    __tablename__ = "shelves"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(150), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    staff = db.relationship("User", secondary=user_shelves, back_populates="shelves", lazy="selectin")
    products = db.relationship("Product", back_populates="shelf", lazy="select")

    @property
    def label(self):
        return f"{self.code} {self.name}"

    def active_staff(self):
        return [u for u in self.staff if u.is_active_user]

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "label": self.label,
            "location": self.location,
            "is_active": self.is_active,
            "product_count": sum(1 for p in self.products if p.is_active),
            "staff": [
                {"id": u.id, "name": u.display_name, "role": u.role}
                for u in self.staff if u.is_active_user
            ],
        }

    def __repr__(self):
        return f"<Shelf {self.code}>"
