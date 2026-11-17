
from datetime import datetime, timezone

from app.extensions import db


class Inventory(db.Model):

    __tablename__ = "inventory"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id"),
        unique=True,
        nullable=False
    )

    quantity = db.Column(
        db.Integer,
        nullable=False,
        default=0
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        db.CheckConstraint(
            "quantity >= 0",
            name="check_inventory_nonnegative"
        ),
    )

    def to_dict(self):

        return {
            "id": self.id,
            "product_id": self.product_id,
            "quantity": self.quantity,
            "updated_at": (
                self.updated_at.isoformat()
                if self.updated_at else None
            )
        }


class StockMovement(db.Model):

    __tablename__ = "stock_movements"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id"),
        nullable=False,
        index=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    movement_type = db.Column(
        db.String(20),
        nullable=False
    )

    quantity = db.Column(
        db.Integer,
        nullable=False
    )

    previous_quantity = db.Column(
        db.Integer,
        nullable=False
    )

    new_quantity = db.Column(
        db.Integer,
        nullable=False
    )

    notes = db.Column(
        db.Text,
        nullable=True
    )

    reference_number = db.Column(
        db.String(100),
        nullable=True
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True
    )

    __table_args__ = (
        db.CheckConstraint(
            "quantity > 0",
            name="check_movement_positive"
        ),
        db.CheckConstraint(
            "previous_quantity >= 0 AND new_quantity >= 0",
            name="check_movement_stock_nonnegative"
        ),
        db.CheckConstraint(
            "movement_type IN ('STOCK_IN', 'STOCK_OUT', 'ADJUSTMENT')",
            name="check_movement_type"
        ),
    )

    def to_dict(self):

        return {
            "id": self.id,
            "product_id": self.product_id,
            "user_id": self.user_id,
            "movement_type": self.movement_type,
            "quantity": self.quantity,
            "previous_quantity": self.previous_quantity,
            "new_quantity": self.new_quantity,
            "product_name": self.product.name if self.product else None,
            "sku": self.product.sku if self.product else None,
            "username": self.user.username if self.user else None,
            "notes": self.notes,
            "reference_number": self.reference_number,
            "created_at": (
                self.created_at.isoformat()
                if self.created_at else None
            )
        }

class StockVerification(db.Model):

    __tablename__ = "stock_verifications"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id"),
        nullable=True,
        index=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    barcode = db.Column(
        db.String(100),
        nullable=False,
        index=True
    )

    expected_quantity = db.Column(
        db.Integer,
        nullable=True
    )

    physical_quantity = db.Column(
        db.Integer,
        nullable=False
    )

    discrepancy = db.Column(
        db.Integer,
        nullable=True
    )

    risk_score = db.Column(
        db.Float,
        nullable=True
    )

    risk_level = db.Column(
        db.String(20),
        nullable=True
    )

    status = db.Column(
        db.String(30),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True
    )

    product = db.relationship("Product", lazy="joined")
    user = db.relationship("User", lazy="joined")

    def to_dict(self):

        return {
            "id": self.id,
            "product_id": self.product_id,
            "user_id": self.user_id,
            "barcode": self.barcode,
            "expected_quantity": self.expected_quantity,
            "physical_quantity": self.physical_quantity,
            "discrepancy": self.discrepancy,
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "status": self.status,
            "product_name": self.product.name if self.product else None,
            "username": self.user.username if self.user else None,
            "created_at": (
                self.created_at.isoformat()
                if self.created_at else None
            )
        }
