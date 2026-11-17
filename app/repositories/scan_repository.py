
from app.extensions import db
from app.models.inventory import StockVerification


class ScanRepository:

    @staticmethod
    def create(data):

        verification = StockVerification(**data)

        db.session.add(verification)
        db.session.flush()

        return verification

    @staticmethod
    def get_by_id(scan_id):

        return db.session.get(
            StockVerification,
            scan_id
        )

    @staticmethod
    def get_all(limit=100):

        return (
            StockVerification.query
            .order_by(
                StockVerification.created_at.desc()
            )
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_by_product(product_id):

        return (
            StockVerification.query
            .filter_by(product_id=product_id)
            .order_by(
                StockVerification.created_at.desc()
            )
            .all()
        )

    @staticmethod
    def get_discrepancies(limit=100):

        return (
            StockVerification.query
            .filter(
                StockVerification.status.in_(
                    ["DISCREPANCY", "UNKNOWN_BARCODE"]
                )
            )
            .order_by(
                StockVerification.created_at.desc()
            )
            .limit(limit)
            .all()
        )

    @staticmethod
    def count():

        return StockVerification.query.count()
