
from app.extensions import db
from app.utils.audit import log_action
from app.services.check_service import CheckService
from app.services.notification_service import NotificationService
from app.repositories.product_repository import ProductRepository
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.scan_repository import ScanRepository
from app.services.risk_service import RiskService
from app.utils.validators import validate_quantity


class VerificationService:

    @staticmethod
    def verify(barcode, physical_quantity, user_id):
        barcode = str(barcode or "").strip()

        if not barcode:
            raise ValueError("Barcode is required.")

        try:
            physical_quantity = validate_quantity(physical_quantity)
        except ValueError:
            raise ValueError("Physical quantity must be a non-negative integer.")

        try:
            product = ProductRepository.get_by_barcode(barcode)

            if not product or not product.is_active:
                verification = ScanRepository.create({
                    "product_id": None,
                    "user_id": user_id,
                    "barcode": barcode,
                    "expected_quantity": None,
                    "physical_quantity": physical_quantity,
                    "discrepancy": None,
                    "risk_score": None,
                    "risk_level": None,
                    "status": "UNKNOWN_BARCODE",
                })

                log_action(user_id, "UNKNOWN_BARCODE_SCANNED", "StockVerification", verification.id, f"Unknown barcode scanned: {barcode}")

                NotificationService.notify_roles(
                    ("manager", "admin"),
                    f"Unknown barcode scanned: {barcode}",
                    f"Counted {physical_quantity} unit(s). Add the product or check the label.",
                    category="UNKNOWN_BARCODE",
                    link="/products",
                    exclude_user_id=user_id,
                )

                db.session.commit()

                return {
                    "success": False,
                    "status": "UNKNOWN_BARCODE",
                    "message": "Barcode does not match an active product.",
                    "verification": verification.to_dict(),
                }

            inventory = InventoryRepository.get_by_product(product.id)
            expected_quantity = inventory.quantity if inventory else 0

            result = RiskService.calculate(
                expected_quantity=expected_quantity,
                physical_quantity=physical_quantity,
                reorder_level=product.reorder_level,
            )

            status = (
                "MATCH"
                if result["difference"] == 0
                else "DISCREPANCY"
            )

            verification = ScanRepository.create({
                "product_id": product.id,
                "user_id": user_id,
                "barcode": barcode,
                "expected_quantity": expected_quantity,
                "physical_quantity": physical_quantity,
                "discrepancy": result["difference"],
                "risk_score": result["score"],
                "risk_level": result["level"],
                "status": status,
            })

            log_action(user_id, "STOCK_VERIFIED", "StockVerification", verification.id, (
                    f"Product {product.sku}: expected "
                    f"{expected_quantity}, physical {physical_quantity}, "
                    f"risk {result['score']}"
                ))

            closed_tasks = CheckService.on_verified(product, verification, user_id)

            db.session.commit()

            return {
                "success": True,
                "completed_checks": len(closed_tasks),
                "status": status,
                "product": product.to_dict(),
                "expected_quantity": expected_quantity,
                "physical_quantity": physical_quantity,
                "discrepancy": result["difference"],
                "risk": result,
                "verification": verification.to_dict(),
            }

        except Exception:
            db.session.rollback()
            raise
