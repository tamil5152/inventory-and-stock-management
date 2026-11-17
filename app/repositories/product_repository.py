
from sqlalchemy import or_

from app.extensions import db
from app.models.product import Product
from app.models.inventory import Inventory


class ProductRepository:

    @staticmethod
    def get_all(include_archived=False):

        query = Product.query

        if not include_archived:
            query = query.filter_by(is_active=True)

        return query.order_by(Product.name.asc()).all()

    @staticmethod
    def get_by_id(product_id):

        return db.session.get(Product, product_id)

    @staticmethod
    def get_by_sku(sku):

        return Product.query.filter_by(
            sku=sku
        ).first()

    @staticmethod
    def get_by_barcode(barcode):

        return Product.query.filter_by(
            barcode=barcode
        ).first()

    @staticmethod
    def search(keyword):

        search_term = f"%{keyword.strip()}%"

        return Product.query.filter(
            Product.is_active.is_(True),
            or_(
                Product.name.ilike(search_term),
                Product.sku.ilike(search_term),
                Product.barcode.ilike(search_term),
                Product.category.ilike(search_term)
            )
        ).order_by(Product.name.asc()).all()

    @staticmethod
    def create(product_data):

        product = Product(**product_data)

        db.session.add(product)
        db.session.flush()

        inventory = Inventory(
            product_id=product.id,
            quantity=0
        )

        db.session.add(inventory)
        db.session.flush()

        return product

    @staticmethod
    def update(product, update_data):

        allowed_fields = {
            "name",
            "category",
            "description",
            "unit_price",
            "reorder_level",
            "count_interval_days",
            "supplier_id",
            "shelf_id",
            "barcode"
        }

        for field, value in update_data.items():

            if field in allowed_fields:
                setattr(product, field, value)

        db.session.flush()

        return product

    @staticmethod
    def archive(product):

        product.is_active = False

        db.session.flush()

        return product

    @staticmethod
    def sku_exists(sku, exclude_id=None):

        query = Product.query.filter_by(sku=sku)

        if exclude_id is not None:
            query = query.filter(Product.id != exclude_id)

        return query.first() is not None

    @staticmethod
    def barcode_exists(barcode, exclude_id=None):

        query = Product.query.filter_by(barcode=barcode)

        if exclude_id is not None:
            query = query.filter(Product.id != exclude_id)

        return query.first() is not None

    @staticmethod
    def count():

        return Product.query.filter_by(
            is_active=True
        ).count()