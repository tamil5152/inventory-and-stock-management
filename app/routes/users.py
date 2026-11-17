import re

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.shelf import Shelf
from app.models.user import User
from app.services.notification_service import NotificationService
from app.utils.audit import log_action
from app.utils.decorators import role_required
from app.utils.validators import (
    validate_required, validate_email, validate_role, validate_phone, validate_full_name,
)

users_bp = Blueprint("users", __name__)


def _shelves_from_ids(ids):

    if ids is None:
        return None

    if not isinstance(ids, list):
        raise ValueError("shelf_ids must be a list.")

    try:
        ids = {int(i) for i in ids}
    except (TypeError, ValueError):
        raise ValueError("Invalid shelf selection.")

    shelves = Shelf.query.filter(Shelf.id.in_(ids), Shelf.is_active.is_(True)).all() if ids else []

    if len(shelves) != len(ids):
        raise ValueError("One or more selected shelves do not exist.")

    return shelves


def _welcome(user):

    shelves = ", ".join(s.label for s in user.shelves) or "none yet"
    NotificationService.notify(
        user,
        "Welcome to StockFlow",
        f"Your shelves: {shelves}. Stock checks for these shelves will be sent to you.",
        category="WELCOME",
        link="/checks",
    )
    NotificationService.send_email(
        user.email,
        "Your StockFlow account is ready",
        f"Hello {user.display_name},\n\n"
        f"An account has been created for you.\n\n"
        f"Username: {user.username}\n"
        f"Role:     {user.role.capitalize()}\n"
        f"Shelves:  {shelves}\n\n"
        "Your manager will give you your password. You will get an e-mail whenever "
        "a stock check is assigned to you.",
        link="/login",
    )
    NotificationService.email_admin(
        f"New {user.role} added: {user.display_name}",
        f"Name:    {user.display_name}\nE-mail:  {user.email}\nMobile:  {user.phone or '-'}\n"
        f"Role:    {user.role.capitalize()}\nShelves: {shelves}\nAdded by: {current_user.display_name}",
        link="/users",
    )


@users_bp.get("/")
@login_required
@role_required("admin")
def list_users():

    users = User.query.order_by(User.username.asc()).all()

    return jsonify({"success": True, "data": [u.to_dict() for u in users]})


@users_bp.post("/")
@login_required
@role_required("admin")
def create_user():

    data = request.get_json(silent=True) or {}

    try:
        full_name = validate_full_name(data.get("full_name"))
        email = validate_email(data.get("email"))
        phone = validate_phone(data.get("phone"))
        role = validate_role(data.get("role", "staff"))
        shelves = _shelves_from_ids(data.get("shelf_ids", []))

        username = validate_required(data.get("username"), "Username")
        if len(username) > 80 or not re.fullmatch(r"[A-Za-z0-9._]+", username):
            raise ValueError("Username may contain letters, numbers, dots and underscores.")

        user = User(username=username, email=email, role=role, full_name=full_name, phone=phone)
        user.set_password(str(data.get("password") or ""))
        user.shelves = shelves

    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    try:
        db.session.add(user)
        db.session.flush()
        log_action(current_user.id, "USER_CREATED", "User", user.id,
                   f"{username} ({role}), shelves: {', '.join(s.code for s in shelves) or '-'}")
        _welcome(user)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Username or e-mail already exists."}), 409

    return jsonify({"success": True, "message": "User created.", "data": user.to_dict()}), 201


@users_bp.put("/<int:user_id>")
@login_required
@role_required("admin")
def update_user(user_id):

    user = db.session.get(User, user_id)

    if not user:
        return jsonify({"error": "User not found."}), 404

    data = request.get_json(silent=True) or {}
    added_shelves = []

    try:
        if "full_name" in data:
            user.full_name = validate_full_name(data["full_name"])

        if "email" in data:
            user.email = validate_email(data["email"])

        if "phone" in data:
            user.phone = validate_phone(data["phone"])

        if "role" in data:
            role = validate_role(data["role"])

            if user.id == current_user.id and role != "admin":
                raise ValueError("You cannot remove your own admin role.")

            user.role = role

        if "is_active" in data:
            active = bool(data["is_active"])

            if user.id == current_user.id and not active:
                raise ValueError("You cannot deactivate your own account.")

            user.is_active_user = active

        if data.get("password"):
            user.set_password(str(data["password"]))

        if "shelf_ids" in data:
            shelves = _shelves_from_ids(data["shelf_ids"])
            before = {s.id for s in user.shelves}
            added_shelves = [s for s in shelves if s.id not in before]
            user.shelves = shelves

    except ValueError as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 400

    for shelf in added_shelves:
        NotificationService.notify(
            user,
            f"You are now responsible for shelf {shelf.label}",
            "Stock checks for products on this shelf will be assigned to you.",
            category="SHELF_ASSIGNED",
            link="/checks",
            email=True,
        )

    try:
        log_action(current_user.id, "USER_UPDATED", "User", user.id, user.username)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "That e-mail is already used by another account."}), 409

    return jsonify({"success": True, "message": "User updated.", "data": user.to_dict()})


@users_bp.get("/email-status")
@login_required
@role_required("admin")
def email_status():

    config = current_app.config

    return jsonify({
        "success": True,
        "data": {
            "enabled": NotificationService.email_enabled(),
            "server": config.get("MAIL_SERVER") or None,
            "sender": config.get("MAIL_FROM") or None,
            "admin_email": NotificationService.admin_address() or None,
        },
    })


@users_bp.post("/test-email")
@login_required
@role_required("admin")
def test_email():

    data = request.get_json(silent=True) or {}

    try:
        to_address = validate_email(data.get("to") or NotificationService.admin_address() or current_user.email)
        NotificationService.send_email_now(
            to_address,
            "Test e-mail",
            f"Hello,\n\nThis is a test e-mail sent by {current_user.display_name} from StockFlow.\n"
            "If you can read this, job assignment e-mails will reach you.",
        )
    except (ValueError, RuntimeError) as error:
        return jsonify({"error": str(error)}), 400

    log_action(current_user.id, "TEST_EMAIL_SENT", "User", current_user.id, to_address)
    db.session.commit()

    return jsonify({"success": True, "message": f"Test e-mail sent to {to_address}."})
