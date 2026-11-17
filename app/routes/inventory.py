from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from app.repositories.inventory_repository import InventoryRepository
from app.services.inventory_service import InventoryService
from app.services.verification_service import VerificationService
from app.utils.validators import validate_quantity

inventory_bp = Blueprint("inventory", __name__)


def _parse_int(value, field):

    if isinstance(value, bool):
        raise ValueError(f"{field} must be a whole number.")

    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a whole number.")


def _move(movement_type):

    data = request.get_json(silent=True) or {}

    try:
        if "product_id" not in data or "quantity" not in data:
            raise ValueError("product_id and quantity are required.")

        result = InventoryService.update_stock(
            product_id=_parse_int(data["product_id"], "Product"),
            quantity=_parse_int(data["quantity"], "Quantity"),
            movement_type=movement_type,
            user_id=current_user.id,
            notes=data.get("notes", ""),
            reference_number=data.get("reference_number"),
        )

        return jsonify(result)

    except ValueError as error:
        return jsonify({"error": str(error)}), 400


@inventory_bp.post("/stock-in")
@login_required
def stock_in():
    return _move("STOCK_IN")


@inventory_bp.post("/stock-out")
@login_required
def stock_out():
    return _move("STOCK_OUT")


@inventory_bp.post("/adjust")
@login_required
def adjust():

    if not current_user.has_role("admin", "manager"):
        return jsonify({"error": "Only admins and managers can adjust stock."}), 403

    return _move("ADJUSTMENT")


@inventory_bp.get("/movements")
@login_required
def movements():

    product_id = request.args.get("product_id", type=int)
    limit = min(request.args.get("limit", 100, type=int) or 100, 500)

    rows = InventoryRepository.get_movement_history(product_id, limit)

    return jsonify({
        "success": True,
        "data": [movement.to_dict() for movement in rows],
    })


@inventory_bp.get("/low-stock")
@login_required
def low_stock():

    rows = InventoryRepository.get_low_stock()

    return jsonify({
        "success": True,
        "data": [row.product.to_dict() for row in rows],
    })


@inventory_bp.post("/verify")
@login_required
def verify_stock():

    data = request.get_json(silent=True) or {}

    try:
        physical_quantity = validate_quantity(data.get("physical_quantity"))

        result = VerificationService.verify(
            data.get("barcode", ""),
            physical_quantity,
            current_user.id,
        )

        return jsonify(result)

    except ValueError as error:
        return jsonify({"error": str(error)}), 400
