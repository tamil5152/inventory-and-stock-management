from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.supplier import Supplier
from app.utils.audit import log_action
from app.utils.decorators import role_required
from app.utils.validators import validate_required, validate_email

suppliers_bp = Blueprint("suppliers", __name__)


def _clean(data, partial=False):

    clean = {}

    if not partial or "company_name" in data:
        clean["company_name"] = validate_required(data.get("company_name"), "Company name")[:150]

    if not partial or "phone" in data:
        phone = validate_required(data.get("phone"), "Phone")
        digits = "".join(ch for ch in phone if ch.isdigit())
        if len(digits) < 7 or len(phone) > 20:
            raise ValueError("Enter a valid phone number.")
        clean["phone"] = phone

    if "email" in data:
        email = str(data.get("email") or "").strip()
        clean["email"] = validate_email(email) if email else None

    for field, size in (("contact_person", 100), ("address", 1000), ("tax_id", 30)):
        if field in data:
            value = str(data.get(field) or "").strip()
            clean[field] = value[:size] or None

    return clean


@suppliers_bp.get("/")
@login_required
def list_suppliers():

    include_inactive = request.args.get("inactive") == "1"
    query = Supplier.query

    if not include_inactive:
        query = query.filter_by(is_active=True)

    suppliers = query.order_by(Supplier.company_name.asc()).all()

    return jsonify({"success": True, "data": [s.to_dict() for s in suppliers]})


@suppliers_bp.get("/<int:supplier_id>")
@login_required
def get_supplier(supplier_id):

    supplier = db.session.get(Supplier, supplier_id)

    if not supplier:
        return jsonify({"error": "Supplier not found."}), 404

    data = supplier.to_dict()
    data["products"] = [
        {"id": p.id, "sku": p.sku, "name": p.name, "quantity": p.quantity}
        for p in supplier.products if p.is_active
    ]

    return jsonify({"success": True, "data": data})


@suppliers_bp.post("/")
@login_required
@role_required("admin", "manager")
def create_supplier():

    try:
        clean = _clean(request.get_json(silent=True) or {})
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    supplier = Supplier(**clean)

    try:
        db.session.add(supplier)
        db.session.flush()
        log_action(current_user.id, "SUPPLIER_CREATED", "Supplier", supplier.id, supplier.company_name)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "A supplier with this email or tax ID already exists."}), 409

    return jsonify({"success": True, "message": "Supplier created.", "data": supplier.to_dict()}), 201


@suppliers_bp.put("/<int:supplier_id>")
@login_required
@role_required("admin", "manager")
def update_supplier(supplier_id):

    supplier = db.session.get(Supplier, supplier_id)

    if not supplier:
        return jsonify({"error": "Supplier not found."}), 404

    try:
        clean = _clean(request.get_json(silent=True) or {}, partial=True)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    for field, value in clean.items():
        setattr(supplier, field, value)

    try:
        log_action(current_user.id, "SUPPLIER_UPDATED", "Supplier", supplier.id, supplier.company_name)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "A supplier with this email or tax ID already exists."}), 409

    return jsonify({"success": True, "message": "Supplier updated.", "data": supplier.to_dict()})


@suppliers_bp.post("/<int:supplier_id>/toggle")
@login_required
@role_required("admin", "manager")
def toggle_supplier(supplier_id):

    supplier = db.session.get(Supplier, supplier_id)

    if not supplier:
        return jsonify({"error": "Supplier not found."}), 404

    supplier.is_active = not supplier.is_active
    log_action(
        current_user.id,
        "SUPPLIER_ACTIVATED" if supplier.is_active else "SUPPLIER_DEACTIVATED",
        "Supplier", supplier.id, supplier.company_name,
    )
    db.session.commit()

    return jsonify({"success": True, "data": supplier.to_dict()})
