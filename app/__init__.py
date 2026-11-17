import os

from flask import Flask, jsonify, request, render_template
from flask_wtf.csrf import CSRFError

from config import Config
from app.extensions import db, login_manager, csrf


def create_app(config_class=Config):

    app = Flask(
        __name__,
        instance_path=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "instance"
        )
    )

    app.config.from_object(config_class)

    os.makedirs(app.instance_path, exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Import models so SQLAlchemy knows every table
    from app import models  # noqa: F401

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.products import products_bp
    from app.routes.inventory import inventory_bp
    from app.routes.scanning import scanning_bp
    from app.routes.reports import reports_bp
    from app.routes.suppliers import suppliers_bp
    from app.routes.users import users_bp
    from app.routes.checks import checks_bp
    from app.routes.notifications import notifications_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(products_bp, url_prefix="/api/products")
    app.register_blueprint(inventory_bp, url_prefix="/api/inventory")
    app.register_blueprint(scanning_bp, url_prefix="/api/scanning")
    app.register_blueprint(reports_bp, url_prefix="/api/reports")
    app.register_blueprint(suppliers_bp, url_prefix="/api/suppliers")
    app.register_blueprint(users_bp, url_prefix="/api/users")
    app.register_blueprint(checks_bp, url_prefix="/api/checks")
    app.register_blueprint(notifications_bp, url_prefix="/api/notifications")

    @login_manager.unauthorized_handler
    def unauthorized():

        from flask import redirect, url_for

        if _wants_json():
            return jsonify({"error": "Login required."}), 401

        return redirect(url_for("auth.login", next=request.path))

    @app.context_processor
    def inject_helpers():

        from flask_login import current_user

        def can(*roles):
            return current_user.is_authenticated and current_user.has_role(*roles)

        return {"can": can}

    register_error_handlers(app)
    register_cli(app)

    # Create database tables
    with app.app_context():
        db.create_all()

        from app.schema import upgrade_schema
        upgrade_schema()

    from app.scheduler import start_alert_scheduler
    start_alert_scheduler(app)

    return app


def _wants_json():

    return (
        request.path.startswith("/api/")
        or request.accept_mimetypes.best == "application/json"
    )


def register_error_handlers(app):

    @app.errorhandler(CSRFError)
    def csrf_error(error):

        if _wants_json():
            return jsonify({"error": "CSRF token missing or invalid. Refresh the page."}), 400

        return render_template("error.html", code=400, message=error.description), 400

    @app.errorhandler(403)
    def forbidden(error):

        if _wants_json():
            return jsonify({"error": "You do not have permission for this action."}), 403

        return render_template("error.html", code=403, message="You do not have permission to view this page."), 403

    @app.errorhandler(404)
    def not_found(error):

        if _wants_json():
            return jsonify({"error": "Resource not found."}), 404

        return render_template("error.html", code=404, message="Page not found."), 404

    @app.errorhandler(500)
    def server_error(error):

        db.session.rollback()

        if _wants_json():
            return jsonify({"error": "Internal server error."}), 500

        return render_template("error.html", code=500, message="Something went wrong."), 500


def register_cli(app):

    @app.cli.command("seed-demo")
    def seed_demo_command():
        """Load demo users, suppliers and products."""

        from app.seed import seed_demo_data

        print(seed_demo_data())

    @app.cli.command("run-alerts")
    def run_alerts_command():
        """Scan products and create physical stock-check tasks (use with cron)."""

        from app.services.check_service import CheckService

        print(CheckService.run())

    @app.cli.command("create-admin")
    def create_admin_command():
        """Interactively create an admin account."""

        from app.seed import create_admin_interactive

        create_admin_interactive()
