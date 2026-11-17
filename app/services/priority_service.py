from sqlalchemy import func

from app.extensions import db
from app.models.product import Product
from app.models.inventory import Inventory, StockVerification
from app.services.risk_service import RiskService
from app.utils.dsa import StockPriorityHeap


class PriorityService:
    """Ranks products by risk using a max-priority heap."""

    @staticmethod
    def get_prioritized_products(limit=None):

        latest_verification = (
            db.session.query(
                StockVerification.product_id,
                func.max(StockVerification.id).label("latest_id"),
            )
            .filter(StockVerification.product_id.isnot(None))
            .group_by(StockVerification.product_id)
            .subquery()
        )

        rows = (
            db.session.query(Product, Inventory, StockVerification)
            .join(Inventory, Inventory.product_id == Product.id)
            .outerjoin(
                latest_verification,
                latest_verification.c.product_id == Product.id,
            )
            .outerjoin(
                StockVerification,
                StockVerification.id == latest_verification.c.latest_id,
            )
            .filter(Product.is_active.is_(True))
            .all()
        )

        priority_heap = StockPriorityHeap()
        details = {}

        for product, inventory, verification in rows:

            # Current stock level always counts; a recent bad scan raises it.
            stock_risk = RiskService.stock_level_risk(
                inventory.quantity, product.reorder_level
            )

            scan_risk = (
                verification.risk_score
                if verification and verification.risk_score is not None
                else 0
            )

            score = max(stock_risk, scan_risk)

            priority_heap.add(score, product.id)

            details[product.id] = {
                "product_id": product.id,
                "sku": product.sku,
                "name": product.name,
                "quantity": inventory.quantity,
                "reorder_level": product.reorder_level,
                "last_scan_status": verification.status if verification else None,
                "risk_score": score,
                "risk_level": RiskService.level_for(score),
            }

        prioritized = []

        while priority_heap.size():

            item = priority_heap.get_highest_priority()

            if item["risk_score"] <= 0:
                continue

            prioritized.append(details[item["product_id"]])

            if limit and len(prioritized) >= limit:
                break

        return prioritized
