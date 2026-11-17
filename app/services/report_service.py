
from sqlalchemy import func

from app.extensions import db
from app.models.product import Product
from app.models.inventory import Inventory, StockMovement, StockVerification
from app.models.supplier import Supplier


class ReportService:

    @staticmethod
    def get_dashboard_summary():
        total_products = Product.query.filter_by(
            is_active=True
        ).count()

        total_suppliers = Supplier.query.filter_by(
            is_active=True
        ).count()

        total_units = (
            db.session.query(
                func.coalesce(func.sum(Inventory.quantity), 0)
            )
            .join(Product, Product.id == Inventory.product_id)
            .filter(Product.is_active.is_(True))
            .scalar()
        )

        low_stock_count = (
            db.session.query(func.count(Product.id))
            .join(Inventory, Inventory.product_id == Product.id)
            .filter(
                Product.is_active.is_(True),
                Inventory.quantity <= Product.reorder_level,
            )
            .scalar()
        )

        discrepancy_count = StockVerification.query.filter(
            StockVerification.status == "DISCREPANCY"
        ).count()

        total_stock_value = (
            db.session.query(
                func.coalesce(
                    func.sum(Inventory.quantity * Product.unit_price), 0
                )
            )
            .join(Product, Product.id == Inventory.product_id)
            .filter(Product.is_active.is_(True))
            .scalar()
        )

        recent_movements = (
            StockMovement.query
            .order_by(StockMovement.created_at.desc())
            .limit(8)
            .all()
        )

        return {
            "total_products": total_products,
            "total_suppliers": total_suppliers,
            "total_units": int(total_units or 0),
            "low_stock_count": low_stock_count,
            "discrepancy_count": discrepancy_count,
            "total_stock_value": float(total_stock_value or 0),
            "recent_movements": [
                movement.to_dict() for movement in recent_movements
            ],
        }

    @staticmethod
    def get_stock_report():
        rows = (
            db.session.query(Product, Inventory)
            .join(Inventory, Inventory.product_id == Product.id)
            .filter(Product.is_active.is_(True))
            .order_by(Product.name.asc())
            .all()
        )

        return [
            {
                "product_id": product.id,
                "sku": product.sku,
                "barcode": product.barcode,
                "name": product.name,
                "category": product.category,
                "quantity": inventory.quantity,
                "reorder_level": product.reorder_level,
                "unit_price": float(product.unit_price or 0),
                "stock_value": float(
                    inventory.quantity * product.unit_price
                ),
                "supplier": (
                    product.supplier.company_name
                    if product.supplier else ""
                ),
                "stock_status": product.stock_status,
            }
            for product, inventory in rows
        ]

    @staticmethod
    def get_category_summary():
        rows = (
            db.session.query(
                Product.category,
                func.count(Product.id),
                func.coalesce(func.sum(Inventory.quantity), 0),
                func.coalesce(
                    func.sum(Inventory.quantity * Product.unit_price), 0
                ),
            )
            .join(Inventory, Inventory.product_id == Product.id)
            .filter(Product.is_active.is_(True))
            .group_by(Product.category)
            .order_by(Product.category.asc())
            .all()
        )

        return [
            {
                "category": category,
                "products": count,
                "units": int(units or 0),
                "value": float(value or 0),
            }
            for category, count, units, value in rows
        ]

    @staticmethod
    def get_movement_report(start=None, end=None, movement_type=None, limit=500):
        query = StockMovement.query

        if start:
            query = query.filter(StockMovement.created_at >= start)

        if end:
            query = query.filter(StockMovement.created_at < end)

        if movement_type:
            query = query.filter(StockMovement.movement_type == movement_type)

        movements = (
            query.order_by(StockMovement.created_at.desc())
            .limit(limit)
            .all()
        )

        return [movement.to_dict() for movement in movements]

    @staticmethod
    def get_discrepancy_report(limit=200):
        rows = (
            StockVerification.query
            .filter(StockVerification.status.in_(["DISCREPANCY", "UNKNOWN_BARCODE"]))
            .order_by(StockVerification.created_at.desc())
            .limit(limit)
            .all()
        )

        return [row.to_dict() for row in rows]

    @staticmethod
    def get_movement_trend(days=14):
        from datetime import datetime, timedelta, timezone

        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=days - 1)
        start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)

        buckets = {
            (start + timedelta(days=i)).isoformat(): {"in": 0, "out": 0}
            for i in range(days)
        }

        for movement in StockMovement.query.filter(StockMovement.created_at >= start_dt):
            created = movement.created_at
            key = created.date().isoformat()
            if key not in buckets:
                continue
            if movement.movement_type == "STOCK_IN":
                buckets[key]["in"] += movement.quantity
            elif movement.movement_type == "STOCK_OUT":
                buckets[key]["out"] += movement.quantity

        return [{"date": k, **v} for k, v in buckets.items()]
