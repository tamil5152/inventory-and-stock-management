
from datetime import datetime, timezone

from app.extensions import db


class Product(db.Model):

    __tablename__ = "products"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    sku = db.Column(
        db.String(50),
        unique=True,
        nullable=False,
        index=True
    )

    barcode = db.Column(
        db.String(100),
        unique=True,
        nullable=False,
        index=True
    )

    name = db.Column(
        db.String(150),
        nullable=False,
        index=True
    )

    category = db.Column(
        db.String(100),
        nullable=False
    )

    description = db.Column(
        db.Text
    )

    unit_price = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=0
    )

    reorder_level = db.Column(
        db.Integer,
        nullable=False,
        default=5
    )

    # How often (in days) this product should be physically counted.
    count_interval_days = db.Column(
        db.Integer,
        nullable=False,
        default=30
    )

    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey("suppliers.id"),
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

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships

    inventory = db.relationship(
        "Inventory",
        backref="product",
        uselist=False,
        cascade="all, delete-orphan"
    )

    stock_movements = db.relationship(
        "StockMovement",
        backref="product",
        lazy=True
    )

    supplier = db.relationship(
        "Supplier",
        back_populates="products"
    )

    def to_dict(self):

        return {
            "id": self.id,
            "sku": self.sku,
            "barcode": self.barcode,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "unit_price": float(self.unit_price or 0),
            "reorder_level": self.reorder_level,
            "count_interval_days": self.count_interval_days,
            "supplier_id": self.supplier_id,
            "supplier_name": (
                self.supplier.company_name if self.supplier else None
            ),
            "is_active": self.is_active,
            "quantity": self.quantity,
            "stock_status": self.stock_status,
            "created_at": (
                self.created_at.isoformat()
                if self.created_at else None
            )
        }

    @property
    def quantity(self):

        return self.inventory.quantity if self.inventory else 0

    @property
    def stock_status(self):

        if self.quantity == 0:
            return "OUT_OF_STOCK"

        if self.quantity <= self.reorder_level:
            return "LOW_STOCK"

        return "IN_STOCK"

    def __repr__(self):

        return f"<Product {self.name}>"
