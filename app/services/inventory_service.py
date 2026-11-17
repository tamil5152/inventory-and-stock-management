from app.extensions import db
from app.models.inventory import Inventory, StockMovement
from app.models.product import Product
from app.utils.audit import log_action


class InventoryService:

    MOVEMENT_TYPES = ("STOCK_IN", "STOCK_OUT", "ADJUSTMENT")

    @staticmethod
    def update_stock(
        product_id,
        quantity,
        movement_type,
        user_id,
        notes="",
        reference_number=None
    ):
        """
        STOCK_IN   -> adds `quantity`
        STOCK_OUT  -> removes `quantity`
        ADJUSTMENT -> sets stock to exactly `quantity` (physical count)
        """

        if isinstance(quantity, bool) or not isinstance(quantity, int):
            raise ValueError("Quantity must be an integer.")

        if movement_type not in InventoryService.MOVEMENT_TYPES:
            raise ValueError("Invalid movement type.")

        if movement_type == "ADJUSTMENT":
            if quantity < 0:
                raise ValueError("Counted quantity cannot be negative.")
        elif quantity <= 0:
            raise ValueError("Quantity must be a positive integer.")

        product = db.session.get(Product, product_id)

        if not product or not product.is_active:
            raise ValueError("Product not found.")

        notes = (notes or "").strip()[:500]
        reference_number = (reference_number or "").strip()[:100] or None

        try:
            inventory = (
                Inventory.query
                .filter_by(product_id=product_id)
                .with_for_update()
                .first()
            )

            if not inventory:
                inventory = Inventory(product_id=product_id, quantity=0)
                db.session.add(inventory)
                db.session.flush()

            previous = inventory.quantity

            if movement_type == "STOCK_IN":
                new_quantity = previous + quantity
                moved = quantity
            elif movement_type == "STOCK_OUT":
                new_quantity = previous - quantity
                moved = quantity
            else:
                new_quantity = quantity
                moved = abs(new_quantity - previous)

                if moved == 0:
                    raise ValueError("Counted quantity equals current stock; nothing to adjust.")

            if new_quantity < 0:
                raise ValueError(
                    f"Insufficient stock. Only {previous} unit(s) available."
                )

            inventory.quantity = new_quantity

            movement = StockMovement(
                product_id=product_id,
                user_id=user_id,
                movement_type=movement_type,
                quantity=moved,
                previous_quantity=previous,
                new_quantity=new_quantity,
                notes=notes or None,
                reference_number=reference_number
            )

            db.session.add(movement)
            db.session.flush()

            log_action(
                user_id,
                movement_type,
                "Product",
                product.id,
                f"{product.sku} {product.name}: {previous} -> {new_quantity}."
                + (f" Reason: {notes}" if notes else "")
            )

            if movement_type == "STOCK_OUT":
                from app.services.check_service import CheckService
                CheckService.on_stock_changed(product, new_quantity)

            db.session.commit()

            return {
                "success": True,
                "product_id": product.id,
                "product": product.name,
                "previous_quantity": previous,
                "new_quantity": new_quantity,
                "movement": movement_type,
                "movement_id": movement.id,
                "low_stock": new_quantity <= product.reorder_level,
            }

        except Exception:
            db.session.rollback()
            raise
