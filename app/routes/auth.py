
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash

from app.extensions import db
from app.models.user import User
from app.models.audit import AuditLog

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Enter both username and password.", "danger")
            return render_template("login.html")

        user = User.query.filter_by(username=username).first()

        if (
            user
            and user.is_active
            and user.check_password(password)
        ):
            login_user(user)

            db.session.add(AuditLog(
                user_id=user.id,
                action="LOGIN",
                entity_type="User",
                entity_id=user.id,
                details="User logged in successfully.",
                ip_address=request.remote_addr,
            ))
            db.session.commit()

            next_page = request.args.get("next", "")

            # Prevent redirects to external websites.
            if next_page.startswith("/") and not next_page.startswith("//"):
                return redirect(next_page)

            return redirect(url_for("dashboard.index"))

        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    user_id = current_user.id

    db.session.add(AuditLog(
        user_id=user_id,
        action="LOGOUT",
        entity_type="User",
        entity_id=user_id,
        details="User logged out.",
        ip_address=request.remote_addr,
    ))
    db.session.commit()

    logout_user()
    flash("You have been logged out.", "success")

    return redirect(url_for("auth.login"))
