
from sqlalchemy import func

from app.extensions import db
from app.models.inventory import Inventory, StockMovement


class InventoryRepository:

    @staticmethod
    def get_by_product(product_id):

        return Inventory.query.filter_by(
            product_id=product_id
        ).first()

    @staticmethod
    def get_or_create(product_id):

        inventory = InventoryRepository.get_by_product(
            product_id
        )

        if inventory is None:

            inventory = Inventory(
                product_id=product_id,
                quantity=0
            )

            db.session.add(inventory)
            db.session.flush()

        return inventory

    @staticmethod
    def get_all():

        return Inventory.query.all()

    @staticmethod
    def get_total_units():

        result = db.session.query(
            func.coalesce(func.sum(Inventory.quantity), 0)
        ).scalar()

        return int(result)

    @staticmethod
    def get_low_stock():

        from app.models.product import Product

        return (
            db.session.query(Inventory)
            .join(Product)
            .filter(
                Inventory.quantity <= Product.reorder_level,
                Product.is_active.is_(True)
            )
            .all()
        )

    @staticmethod
    def create_movement(
        product_id,
        user_id,
        movement_type,
        quantity,
        previous_quantity,
        new_quantity,
        notes=None,
        reference_number=None
    ):

        movement = StockMovement(
            product_id=product_id,
            user_id=user_id,
            movement_type=movement_type,
            quantity=quantity,
            previous_quantity=previous_quantity,
            new_quantity=new_quantity,
            notes=notes,
            reference_number=reference_number
        )

        db.session.add(movement)
        db.session.flush()

        return movement

    @staticmethod
    def get_movement_history(product_id=None, limit=100):

        query = StockMovement.query

        if product_id is not None:
            query = query.filter_by(
                product_id=product_id
            )

        return (
            query.order_by(
                StockMovement.created_at.desc()
            )
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_recent_movements(limit=10):

        return (
            StockMovement.query
            .order_by(StockMovement.created_at.desc())
            .limit(limit)
            .all()
        )
