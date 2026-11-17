
from datetime import datetime, timezone

from app.extensions import db


class Supplier(db.Model):

    __tablename__ = "suppliers"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    company_name = db.Column(
        db.String(150),
        nullable=False,
        index=True
    )

    contact_person = db.Column(
        db.String(100)
    )

    email = db.Column(
        db.String(120),
        unique=True,
        nullable=True
    )

    phone = db.Column(
        db.String(20),
        nullable=False
    )

    address = db.Column(
        db.Text
    )

    tax_id = db.Column(
        db.String(30),
        unique=True,
        nullable=True
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    # One supplier can provide multiple products.
    products = db.relationship(
        "Product",
        back_populates="supplier",
        lazy=True
    )

    def to_dict(self):

        return {
            "id": self.id,
            "company_name": self.company_name,
            "contact_person": self.contact_person,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
            "tax_id": self.tax_id,
            "is_active": self.is_active,
            "product_count": len([p for p in self.products if p.is_active]),
            "created_at": (
                self.created_at.isoformat()
                if self.created_at else None
            )
        }

    def __repr__(self):

        return f"<Supplier {self.company_name}>"
