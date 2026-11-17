
from app.models.product import Product
from app.models.inventory import Inventory, StockVerification
from app.extensions import db


class RecommendationService:

    @staticmethod
    def get_recommendations():
        products = (
            db.session.query(Product, Inventory)
            .join(Inventory, Inventory.product_id == Product.id)
            .filter(
                Product.is_active.is_(True),
                Inventory.quantity <= Product.reorder_level,
            )
            .all()
        )

        recommendations = []

        for product, inventory in products:
            current_quantity = inventory.quantity
            reorder_level = product.reorder_level

            # Target stock is twice the configured reorder level.
            target_quantity = max(reorder_level * 2, 1)
            suggested_quantity = max(
                target_quantity - current_quantity, 0
            )

            recommendations.append({
                "product_id": product.id,
                "sku": product.sku,
                "barcode": product.barcode,
                "product_name": product.name,
                "current_quantity": current_quantity,
                "reorder_level": reorder_level,
                "suggested_quantity": suggested_quantity,
                "supplier_id": product.supplier_id,
                "reason": "Current stock has reached the reorder level.",
            })

        return recommendations
