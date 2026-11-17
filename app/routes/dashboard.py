from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user

from app.models.alerts import CheckTask

from app.services.report_service import ReportService
from app.services.recommendation_service import RecommendationService
from app.services.priority_service import PriorityService
from app.utils.decorators import role_required

dashboard_bp = Blueprint("dashboard", __name__)


# ---------------------------------------------------------------
# HTML pages
# ---------------------------------------------------------------

@dashboard_bp.route("/")
@login_required
def index():
    summary = ReportService.get_dashboard_summary()
    recommendations = RecommendationService.get_recommendations()
    priority_products = PriorityService.get_prioritized_products(limit=6)

    is_manager = current_user.has_role("admin", "manager")
    task_query = CheckTask.query.filter(CheckTask.status.in_(["OPEN", "IN_PROGRESS"]))
    if not is_manager:
        task_query = task_query.filter(
            (CheckTask.assigned_to == current_user.id) | (CheckTask.assigned_to.is_(None))
        )
    tasks = task_query.all()
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    tasks.sort(key=lambda t: (order[t.priority], t.due_at or t.created_at))

    checks = {
        "count": len(tasks),
        "high": sum(1 for t in tasks if t.priority == "HIGH"),
        "overdue": sum(1 for t in tasks if t.is_overdue),
        "first": tasks[0].to_dict() if tasks else None,
        "scope": "team" if is_manager else "you",
    }

    return render_template(
        "dashboard.html",
        checks=checks,
        summary=summary,
        recommendations=recommendations,
        priority_products=priority_products,
    )


@dashboard_bp.route("/products")
@login_required
def products_page():
    return render_template("products.html")


@dashboard_bp.route("/inventory")
@login_required
def inventory_page():
    return render_template("inventory.html")


@dashboard_bp.route("/scanner")
@login_required
def scanner_page():
    return render_template("scanner.html")


@dashboard_bp.route("/suppliers")
@login_required
def suppliers_page():
    return render_template("suppliers.html")


@dashboard_bp.route("/reports")
@login_required
def reports_page():
    return render_template("reports.html")


@dashboard_bp.route("/checks")
@login_required
def checks_page():
    return render_template("checks.html")


@dashboard_bp.route("/shelves")
@login_required
def shelves_page():
    return render_template("shelves.html")


@dashboard_bp.route("/users")
@login_required
@role_required("admin")
def users_page():
    return render_template("users.html")


# ---------------------------------------------------------------
# Dashboard JSON
# ---------------------------------------------------------------

@dashboard_bp.route("/api/summary")
@login_required
def summary():
    return jsonify({
        "success": True,
        "data": ReportService.get_dashboard_summary(),
    })


@dashboard_bp.route("/api/priorities")
@login_required
def priorities():
    return jsonify({
        "success": True,
        "data": PriorityService.get_prioritized_products(),
    })


@dashboard_bp.route("/api/charts")
@login_required
def charts():
    return jsonify({
        "success": True,
        "data": {
            "categories": ReportService.get_category_summary(),
            "trend": ReportService.get_movement_trend(days=14),
        },
    })


@dashboard_bp.route("/api/recommendations")
@login_required
def recommendations():
    return jsonify({
        "success": True,
        "data": RecommendationService.get_recommendations(),
    })
