from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.user import User
from app.utils.audit import log_action
from app.utils.decorators import role_required
from app.utils.validators import validate_required, validate_email, validate_role

users_bp = Blueprint("users", __name__)


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
        username = validate_required(data.get("username"), "Username")

        if len(username) > 80 or not username.replace("_", "").replace(".", "").isalnum():
            raise ValueError("Username may contain letters, numbers, dots and underscores.")

        email = validate_email(data.get("email"))
        role = validate_role(data.get("role", "staff"))
        password = str(data.get("password") or "")

        user = User(username=username, email=email, role=role)
        user.set_password(password)

    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    try:
        db.session.add(user)
        db.session.flush()
        log_action(current_user.id, "USER_CREATED", "User", user.id, f"{username} ({role})")
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Username or email already exists."}), 409

    return jsonify({"success": True, "message": "User created.", "data": user.to_dict()}), 201


@users_bp.put("/<int:user_id>")
@login_required
@role_required("admin")
def update_user(user_id):

    user = db.session.get(User, user_id)

    if not user:
        return jsonify({"error": "User not found."}), 404

    data = request.get_json(silent=True) or {}

    try:
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

    except ValueError as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 400

    log_action(current_user.id, "USER_UPDATED", "User", user.id, user.username)
    db.session.commit()

    return jsonify({"success": True, "message": "User updated.", "data": user.to_dict()})
