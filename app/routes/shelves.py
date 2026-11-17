import re

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.shelf import Shelf
from app.models.user import User
from app.services.notification_service import NotificationService
from app.utils.audit import log_action
from app.utils.decorators import role_required
from app.utils.validators import validate_required

shelves_bp = Blueprint("shelves", __name__)


def _clean(data, partial=False):

    clean = {}

    if not partial or "code" in data:
        code = validate_required(data.get("code"), "Shelf code").upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9\-]{0,19}", code):
            raise ValueError("Shelf code may use letters, numbers and hyphens (max 20), for example A1 or RACK-2.")
        clean["code"] = code

    if not partial or "name" in data:
        name = validate_required(data.get("name"), "Shelf name")
        if len(name) > 100:
            raise ValueError("Shelf name must be at most 100 characters.")
        clean["name"] = name

    if "location" in data:
        clean["location"] = str(data.get("location") or "").strip()[:150] or None

    return clean


def _staff_from_ids(ids):

    if ids is None:
        return None

    if not isinstance(ids, list):
        raise ValueError("staff_ids must be a list.")

    try:
        ids = {int(i) for i in ids}
    except (TypeError, ValueError):
        raise ValueError("Invalid staff selection.")

    users = User.query.filter(User.id.in_(ids), User.is_active_user.is_(True)).all() if ids else []

    if len(users) != len(ids):
        raise ValueError("One or more selected people are not active users.")

    return users


def _notify_new_staff(shelf, added):

    for user in added:
        NotificationService.notify(
            user,
            f"You are now responsible for shelf {shelf.label}",
            "Stock checks for products on this shelf will be assigned to you.",
            category="SHELF_ASSIGNED",
            link="/checks",
            email=True,
        )


@shelves_bp.get("/")
@login_required
def list_shelves():

    query = Shelf.query
    if request.args.get("inactive") != "1":
        query = query.filter_by(is_active=True)

    return jsonify({"success": True, "data": [s.to_dict() for s in query.order_by(Shelf.code).all()]})


@shelves_bp.post("/")
@login_required
@role_required("admin", "manager")
def create_shelf():

    data = request.get_json(silent=True) or {}

    try:
        clean = _clean(data)
        staff = _staff_from_ids(data.get("staff_ids", []))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    shelf = Shelf(**clean)
    shelf.staff = staff or []

    try:
        db.session.add(shelf)
        db.session.flush()
        _notify_new_staff(shelf, shelf.staff)
        log_action(current_user.id, "SHELF_CREATED", "Shelf", shelf.id, shelf.label)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "A shelf with this code already exists."}), 409

    return jsonify({"success": True, "message": "Shelf created.", "data": shelf.to_dict()}), 201


@shelves_bp.put("/<int:shelf_id>")
@login_required
@role_required("admin", "manager")
def update_shelf(shelf_id):

    shelf = db.session.get(Shelf, shelf_id)
    if not shelf:
        return jsonify({"error": "Shelf not found."}), 404

    data = request.get_json(silent=True) or {}

    try:
        clean = _clean(data, partial=True)
        staff = _staff_from_ids(data.get("staff_ids"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    for field, value in clean.items():
        setattr(shelf, field, value)

    added = []
    if staff is not None:
        before = {u.id for u in shelf.staff}
        added = [u for u in staff if u.id not in before]
        shelf.staff = staff

    try:
        db.session.flush()
        _notify_new_staff(shelf, added)
        log_action(current_user.id, "SHELF_UPDATED", "Shelf", shelf.id, shelf.label)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "A shelf with this code already exists."}), 409

    return jsonify({"success": True, "message": "Shelf updated.", "data": shelf.to_dict()})


@shelves_bp.post("/<int:shelf_id>/toggle")
@login_required
@role_required("admin", "manager")
def toggle_shelf(shelf_id):

    shelf = db.session.get(Shelf, shelf_id)
    if not shelf:
        return jsonify({"error": "Shelf not found."}), 404

    shelf.is_active = not shelf.is_active
    log_action(current_user.id, "SHELF_ACTIVATED" if shelf.is_active else "SHELF_DEACTIVATED", "Shelf", shelf.id, shelf.label)
    db.session.commit()

    return jsonify({"success": True, "data": shelf.to_dict()})
