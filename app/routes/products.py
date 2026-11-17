from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.product import Product
from app.models.supplier import Supplier
from app.repositories.product_repository import ProductRepository
from app.utils.audit import log_action
from app.utils.decorators import role_required
from app.utils.dsa import binary_search
from app.utils.validators import (
    validate_required,
    validate_sku,
    validate_barcode,
    validate_price,
    validate_quantity,
)

products_bp = Blueprint("products", __name__)


def _clean_product_payload(data, partial=False):
    """Validate incoming product JSON. Returns a dict of clean fields."""

    clean = {}

    def present(field):
        return field in data and data[field] is not None

    if not partial or present("sku"):
        clean["sku"] = validate_sku(data.get("sku"))

    if not partial or present("barcode"):
        clean["barcode"] = validate_barcode(data.get("barcode"))

    if not partial or present("name"):
        name = validate_required(data.get("name"), "Name")
        if len(name) > 150:
            raise ValueError("Name must be at most 150 characters.")
        clean["name"] = name

    if not partial or present("category"):
        category = str(data.get("category") or "General").strip() or "General"
        clean["category"] = category[:100]

    if present("description"):
        clean["description"] = str(data["description"]).strip()[:2000]

    if not partial or present("unit_price"):
        clean["unit_price"] = validate_price(data.get("unit_price", 0) or 0)

    if not partial or present("reorder_level"):
        clean["reorder_level"] = validate_quantity(data.get("reorder_level", 5))

    if not partial or present("count_interval_days"):
        raw_interval = data.get("count_interval_days")
        interval = validate_quantity(30 if raw_interval in (None, "") else raw_interval)
        if not 1 <= interval <= 365:
            raise ValueError("Count cycle must be between 1 and 365 days.")
        clean["count_interval_days"] = interval

    if "supplier_id" in data:
        supplier_id = data.get("supplier_id")

        if supplier_id in (None, "", 0, "0"):
            clean["supplier_id"] = None
        else:
            try:
                supplier_id = int(supplier_id)
            except (TypeError, ValueError):
                raise ValueError("Invalid supplier.")

            supplier = db.session.get(Supplier, supplier_id)

            if not supplier or not supplier.is_active:
                raise ValueError("Supplier not found.")

            clean["supplier_id"] = supplier_id

    return clean


@products_bp.get("/")
@login_required
def get_products():

    keyword = request.args.get("q", "").strip()
    include_archived = request.args.get("archived") == "1"
    status = request.args.get("status", "").upper()
    category = request.args.get("category", "").strip()

    if keyword:
        products = ProductRepository.search(keyword)
    else:
        products = ProductRepository.get_all(include_archived=include_archived)

    if category:
        products = [p for p in products if p.category == category]

    if status in ("IN_STOCK", "LOW_STOCK", "OUT_OF_STOCK"):
        products = [p for p in products if p.stock_status == status]

    categories = sorted({
        row[0] for row in db.session.query(Product.category)
        .filter(Product.is_active.is_(True)).distinct()
    })

    return jsonify({
        "success": True,
        "data": [product.to_dict() for product in products],
        "categories": categories,
    })


@products_bp.get("/<int:product_id>")
@login_required
def get_product(product_id):

    product = ProductRepository.get_by_id(product_id)

    if not product:
        return jsonify({"error": "Product not found."}), 404

    return jsonify({"success": True, "data": product.to_dict()})


@products_bp.get("/barcode/<string:barcode>")
@login_required
def get_by_barcode(barcode):

    product = ProductRepository.get_by_barcode(barcode.strip())

    if not product or not product.is_active:
        return jsonify({"error": "No active product with this barcode."}), 404

    return jsonify({"success": True, "data": product.to_dict()})


@products_bp.get("/sku/<string:sku>")
@login_required
def get_by_sku(sku):
    """SKU lookup using binary search over the SKU-sorted product list."""

    products = sorted(
        (p.to_dict() for p in ProductRepository.get_all()),
        key=lambda p: p["sku"]
    )

    product = binary_search(products, sku.strip().upper())

    if not product:
        return jsonify({"error": "No active product with this SKU."}), 404

    return jsonify({"success": True, "data": product})


@products_bp.post("/")
@login_required
@role_required("admin", "manager")
def add_product():

    data = request.get_json(silent=True) or {}

    try:
        clean = _clean_product_payload(data)
        opening_quantity = validate_quantity(data.get("quantity", 0) or 0)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    if ProductRepository.sku_exists(clean["sku"]):
        return jsonify({"error": "SKU already exists."}), 409

    if ProductRepository.barcode_exists(clean["barcode"]):
        return jsonify({"error": "Barcode already exists."}), 409

    try:
        product = ProductRepository.create(clean)

        if opening_quantity:
            product.inventory.quantity = opening_quantity

            from app.models.inventory import StockMovement

            db.session.add(StockMovement(
                product_id=product.id,
                user_id=current_user.id,
                movement_type="STOCK_IN",
                quantity=opening_quantity,
                previous_quantity=0,
                new_quantity=opening_quantity,
                notes="Opening stock",
            ))

        log_action(
            current_user.id, "PRODUCT_CREATED", "Product", product.id,
            f"{product.sku} {product.name} created with {opening_quantity} unit(s)."
        )

        db.session.commit()

    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "SKU or barcode already exists."}), 409

    return jsonify({
        "success": True,
        "message": "Product created successfully.",
        "data": product.to_dict(),
    }), 201


@products_bp.put("/<int:product_id>")
@login_required
@role_required("admin", "manager")
def update_product(product_id):

    product = ProductRepository.get_by_id(product_id)

    if not product:
        return jsonify({"error": "Product not found."}), 404

    data = request.get_json(silent=True) or {}

    try:
        clean = _clean_product_payload(data, partial=True)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    if "sku" in clean and clean["sku"] != product.sku:
        return jsonify({"error": "SKU cannot be changed after creation."}), 400

    clean.pop("sku", None)

    if "barcode" in clean and ProductRepository.barcode_exists(
        clean["barcode"], exclude_id=product.id
    ):
        return jsonify({"error": "Barcode already exists."}), 409

    try:
        ProductRepository.update(product, clean)
        log_action(
            current_user.id, "PRODUCT_UPDATED", "Product", product.id,
            f"Updated fields: {', '.join(sorted(clean)) or 'none'}"
        )
        db.session.commit()

    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Barcode already exists."}), 409

    return jsonify({
        "success": True,
        "message": "Product updated.",
        "data": product.to_dict(),
    })


@products_bp.post("/<int:product_id>/archive")
@login_required
@role_required("admin", "manager")
def archive_product(product_id):

    product = ProductRepository.get_by_id(product_id)

    if not product:
        return jsonify({"error": "Product not found."}), 404

    ProductRepository.archive(product)
    log_action(current_user.id, "PRODUCT_ARCHIVED", "Product", product.id, product.sku)
    db.session.commit()

    return jsonify({"success": True, "message": "Product archived."})


@products_bp.post("/<int:product_id>/restore")
@login_required
@role_required("admin", "manager")
def restore_product(product_id):

    product = ProductRepository.get_by_id(product_id)

    if not product:
        return jsonify({"error": "Product not found."}), 404

    product.is_active = True
    log_action(current_user.id, "PRODUCT_RESTORED", "Product", product.id, product.sku)
    db.session.commit()

    return jsonify({"success": True, "message": "Product restored."})


@products_bp.delete("/<int:product_id>")
@login_required
@role_required("admin")
def delete_product(product_id):

    product = ProductRepository.get_by_id(product_id)

    if not product:
        return jsonify({"error": "Product not found."}), 404

    if product.stock_movements:
        return jsonify({
            "error": "Product has stock history. Archive it instead of deleting."
        }), 409

    sku = product.sku

    from app.models.inventory import StockVerification

    StockVerification.query.filter_by(product_id=product.id).update(
        {"product_id": None}
    )

    db.session.delete(product)
    log_action(current_user.id, "PRODUCT_DELETED", "Product", product_id, sku)
    db.session.commit()

    return jsonify({"success": True, "message": "Product deleted."})
