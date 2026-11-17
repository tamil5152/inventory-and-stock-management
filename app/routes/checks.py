from datetime import datetime, timezone

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import case

from app.extensions import db
from app.models.alerts import CheckTask
from app.models.product import Product
from app.models.user import User
from app.services.check_service import CheckService
from app.services.notification_service import NotificationService
from app.utils.audit import log_action
from app.utils.decorators import role_required

checks_bp = Blueprint("checks", __name__)


def _is_manager():
    return current_user.has_role("admin", "manager")


def _get_task(task_id):

    task = db.session.get(CheckTask, task_id)

    if not task:
        return None, (jsonify({"error": "Stock check not found."}), 404)

    if not _is_manager() and task.assigned_to not in (None, current_user.id):
        return None, (jsonify({"error": "This stock check is assigned to someone else."}), 403)

    return task, None


@checks_bp.get("/")
@login_required
def list_checks():

    scope = request.args.get("scope", "mine" if not _is_manager() else "all")
    status = request.args.get("status", "open").lower()

    query = CheckTask.query

    if scope == "mine" or not _is_manager():
        query = query.filter(
            (CheckTask.assigned_to == current_user.id) | (CheckTask.assigned_to.is_(None))
        )

    if status == "open":
        query = query.filter(CheckTask.status.in_(["OPEN", "IN_PROGRESS"]))
    elif status == "done":
        query = query.filter(CheckTask.status.in_(["DONE", "CANCELLED"]))

    priority_order = case((CheckTask.priority == "HIGH", 0), (CheckTask.priority == "MEDIUM", 1), else_=2)

    if status == "done":
        query = query.order_by(CheckTask.completed_at.desc(), CheckTask.id.desc())
    else:
        query = query.order_by(priority_order, CheckTask.due_at.asc())

    tasks = query.limit(300).all()

    return jsonify({
        "success": True,
        "data": [task.to_dict() for task in tasks],
        "summary": CheckService.open_counts(),
    })


@checks_bp.get("/summary")
@login_required
def summary():

    mine = CheckTask.query.filter(
        CheckTask.assigned_to == current_user.id,
        CheckTask.status.in_(["OPEN", "IN_PROGRESS"]),
    ).all()

    return jsonify({
        "success": True,
        "data": {
            **CheckService.open_counts(),
            "mine": len(mine),
            "mine_overdue": sum(1 for t in mine if t.is_overdue),
        },
    })


@checks_bp.post("/")
@login_required
@role_required("admin", "manager")
def create_check():

    data = request.get_json(silent=True) or {}

    try:
        product = db.session.get(Product, int(data.get("product_id")))
    except (TypeError, ValueError):
        product = None

    if not product or not product.is_active:
        return jsonify({"error": "Select an active product."}), 400

    if CheckService.open_task_for(product.id):
        return jsonify({"error": "This product already has an open stock check."}), 409

    priority = str(data.get("priority", "MEDIUM")).upper()
    if priority not in CheckTask.PRIORITIES:
        return jsonify({"error": "Invalid priority."}), 400

    assignee = None
    if data.get("assigned_to"):
        assignee = db.session.get(User, int(data["assigned_to"]))
        if not assignee or not assignee.is_active_user:
            return jsonify({"error": "Selected user is not active."}), 400

    due_at = None
    if data.get("due_at"):
        try:
            due_at = datetime.fromisoformat(str(data["due_at"]))
            if due_at.tzinfo is None:
                due_at = due_at.replace(tzinfo=timezone.utc)
        except ValueError:
            return jsonify({"error": "Invalid due date."}), 400

    task = CheckService.create_task(
        product, "MANUAL", priority,
        assignee=assignee, created_by=current_user,
        note=data.get("note"), due_at=due_at,
    )
    log_action(current_user.id, "CHECK_CREATED", "CheckTask", task.id, f"{product.sku} -> {task.assignee.username if task.assignee else 'unassigned'}")
    db.session.commit()

    return jsonify({"success": True, "message": "Stock check created.", "data": task.to_dict()}), 201


@checks_bp.post("/run")
@login_required
@role_required("admin", "manager")
def run_scan():

    result = CheckService.run(actor=current_user)

    return jsonify({"success": True, "data": result})


@checks_bp.post("/<int:task_id>/start")
@login_required
def start_check(task_id):

    task, error = _get_task(task_id)
    if error:
        return error

    if not task.is_open:
        return jsonify({"error": "This stock check is already closed."}), 400

    task.status = "IN_PROGRESS"
    if task.assigned_to is None:
        task.assigned_to = current_user.id
    db.session.commit()

    return jsonify({"success": True, "data": task.to_dict()})


@checks_bp.put("/<int:task_id>")
@login_required
@role_required("admin", "manager")
def update_check(task_id):

    task = db.session.get(CheckTask, task_id)
    if not task:
        return jsonify({"error": "Stock check not found."}), 404

    data = request.get_json(silent=True) or {}

    if "assigned_to" in data:
        assignee = db.session.get(User, int(data["assigned_to"])) if data["assigned_to"] else None
        if data["assigned_to"] and (not assignee or not assignee.is_active_user):
            return jsonify({"error": "Selected user is not active."}), 400

        if assignee and assignee.id != task.assigned_to:
            NotificationService.notify(
                assignee,
                f"Count {task.product.name} ({task.product.sku})",
                f"{current_user.username} assigned this stock check to you.",
                category="CHECK_ASSIGNED",
                link=f"/scanner?barcode={task.product.barcode}&task={task.id}",
                email=True,
            )
        task.assigned_to = assignee.id if assignee else None
        task.overdue_notified = False

    if "priority" in data:
        priority = str(data["priority"]).upper()
        if priority not in CheckTask.PRIORITIES:
            return jsonify({"error": "Invalid priority."}), 400
        task.priority = priority

    if "note" in data:
        task.note = str(data["note"] or "").strip()[:1000] or None

    db.session.commit()

    return jsonify({"success": True, "message": "Stock check updated.", "data": task.to_dict()})


@checks_bp.post("/<int:task_id>/cancel")
@login_required
@role_required("admin", "manager")
def cancel_check(task_id):

    task = db.session.get(CheckTask, task_id)
    if not task:
        return jsonify({"error": "Stock check not found."}), 404

    if not task.is_open:
        return jsonify({"error": "This stock check is already closed."}), 400

    task.status = "CANCELLED"
    task.completed_by = current_user.id
    task.completed_at = datetime.now(timezone.utc)
    log_action(current_user.id, "CHECK_CANCELLED", "CheckTask", task.id, task.product.sku)
    db.session.commit()

    return jsonify({"success": True, "message": "Stock check cancelled."})


@checks_bp.get("/assignees")
@login_required
@role_required("admin", "manager")
def assignees():

    users = User.query.filter(User.is_active_user.is_(True)).order_by(User.role.desc(), User.username).all()

    return jsonify({
        "success": True,
        "data": [{"id": u.id, "username": u.username, "role": u.role} for u in users],
    })
