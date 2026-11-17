"""
Physical stock-check alerts.

Scans the catalogue and creates CheckTask records asking staff to physically
count a product when:
  * stock is zero or at/below the reorder level and nobody has counted it since
    the last stock movement,
  * the latest count found a discrepancy that was never resolved (no adjustment
    and no clean recount for a day),
  * the product has never been counted, or its count cycle has expired.

Each new task goes to a staff member responsible for the product's shelf
(the least busy one), falling back to any staff member, then managers.
The assignee gets an in-app notification and an e-mail, and the admin mailbox
(ADMIN_EMAIL) gets a copy of the assignment.
"""

from datetime import datetime, timedelta, timezone

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import current_app
from sqlalchemy import func

from app.extensions import db
from app.models.alerts import CheckTask
from app.models.inventory import Inventory, StockMovement, StockVerification
from app.models.product import Product
from app.models.user import User
from app.services.notification_service import NotificationService
from app.utils.audit import log_action
from app.utils.dsa import StockPriorityHeap


PRIORITY_SCORE = {"HIGH": 90, "MEDIUM": 60, "LOW": 30}
DUE_HOURS = {"HIGH": 8, "MEDIUM": 24, "LOW": 72}


def _utc(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _now():
    return datetime.now(timezone.utc)


def _local(value):
    """Format a UTC datetime in DISPLAY_TIMEZONE for e-mails, e.g. '18 Nov 2026, 06:46 IST'."""

    if value is None:
        return "-"

    name = current_app.config.get("DISPLAY_TIMEZONE") or "UTC"
    try:
        zone = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        zone = timezone.utc

    return _utc(value).astimezone(zone).strftime("%d %b %Y, %I:%M %p %Z")


class CheckService:

    # -------------------------------------------------------------
    # Queries
    # -------------------------------------------------------------

    @staticmethod
    def open_task_for(product_id):
        return CheckTask.query.filter(
            CheckTask.product_id == product_id,
            CheckTask.status.in_(["OPEN", "IN_PROGRESS"]),
        ).first()

    @staticmethod
    def open_counts():
        open_q = CheckTask.query.filter(CheckTask.status.in_(["OPEN", "IN_PROGRESS"]))
        tasks = open_q.all()
        return {
            "open": len(tasks),
            "high": sum(1 for t in tasks if t.priority == "HIGH"),
            "overdue": sum(1 for t in tasks if t.is_overdue),
        }

    @staticmethod
    def _least_busy(users):

        load = dict(
            db.session.query(CheckTask.assigned_to, func.count(CheckTask.id))
            .filter(CheckTask.status.in_(["OPEN", "IN_PROGRESS"]))
            .group_by(CheckTask.assigned_to)
            .all()
        )
        return min(users, key=lambda u: (load.get(u.id, 0), u.id))

    @staticmethod
    def pick_assignee(product=None):
        """
        1. Active people assigned to the product's shelf (staff before managers).
        2. Otherwise any active staff member, then managers, then admins.
        The least busy person in the first non-empty group wins.
        """

        shelf = product.shelf if product is not None else None

        if shelf is not None and shelf.is_active:
            shelf_people = shelf.active_staff()
            for roles in (("staff",), ("manager", "admin")):
                group = [u for u in shelf_people if u.role in roles]
                if group:
                    return CheckService._least_busy(group)

        for roles in (("staff",), ("manager",), ("admin",)):
            users = User.query.filter(
                User.role.in_(roles), User.is_active_user.is_(True)
            ).all()

            if users:
                return CheckService._least_busy(users)

        return None

    @staticmethod
    def describe_assignment(task):
        """Plain-text lines describing who has to count what, for e-mails."""

        product = task.product
        shelf = product.shelf
        person = task.assignee

        lines = [
            f"Product:   {product.name} ({product.sku})",
            f"Barcode:   {product.barcode}",
            f"Shelf:     {shelf.label + (' - ' + shelf.location if shelf.location else '') if shelf else 'Not set'}",
            f"Reason:    {CheckTask.REASONS.get(task.reason, task.reason)}",
            f"Priority:  {task.priority.capitalize()}",
            f"Due:       {_local(task.due_at)}",
        ]

        if person:
            lines += [
                "",
                f"Assigned to: {person.display_name}",
                f"E-mail:      {person.email}",
                f"Mobile:      {person.phone or 'Not given'}",
            ]
        else:
            lines += ["", "Assigned to: nobody (add staff to this shelf)"]

        return "\n".join(lines)

    @staticmethod
    def email_admin_assignment(task, heading="New job assigned"):

        person = task.assignee.display_name if task.assignee else "nobody"
        NotificationService.email_admin(
            f"{heading}: {task.product.name} to {person}",
            f"A stock check has been assigned.\n\n{CheckService.describe_assignment(task)}",
            link="/checks",
        )

    # -------------------------------------------------------------
    # Creating tasks
    # -------------------------------------------------------------

    @staticmethod
    def create_task(product, reason, priority, assignee=None, created_by=None, note=None, due_at=None,
                    notify=True, admin_email=True):

        if assignee is None:
            assignee = CheckService.pick_assignee(product)

        task = CheckTask(
            product_id=product.id,
            assigned_to=assignee.id if assignee else None,
            created_by=created_by.id if created_by else None,
            reason=reason,
            priority=priority,
            note=(note or "").strip()[:1000] or None,
            due_at=due_at or (_now() + timedelta(hours=DUE_HOURS[priority])),
        )
        db.session.add(task)
        db.session.flush()

        if notify and assignee:
            shelf_text = f" on shelf {product.shelf.label}" if product.shelf else ""
            NotificationService.notify(
                assignee,
                f"Count {product.name} ({product.sku}){shelf_text}",
                f"{CheckTask.REASONS.get(reason, reason)}. Please count the shelf and record "
                f"the physical quantity. Priority: {priority.lower()}.",
                category="CHECK_ASSIGNED",
                link=f"/scanner?barcode={product.barcode}&task={task.id}",
            )
            NotificationService.send_email(
                assignee.email,
                f"New job: count {product.name}{shelf_text}",
                f"Hello {assignee.display_name},\n\nYou have a new stock check.\n\n"
                f"{CheckService.describe_assignment(task)}\n\n"
                "Open the link, scan the barcode, count the shelf and enter the number.",
                link=f"/scanner?barcode={product.barcode}&task={task.id}",
            )

        if notify and admin_email:
            CheckService.email_admin_assignment(task)

        return task

    @staticmethod
    def evaluate_product(product, inventory, latest_scan, last_movement_at):
        """Return (reason, priority) if the product needs a physical check, else None."""

        now = _now()
        quantity = inventory.quantity if inventory else 0
        last_count_at = _utc(latest_scan.created_at) if latest_scan else None
        last_movement_at = _utc(last_movement_at)
        counted_since_movement = (
            last_count_at is not None
            and (last_movement_at is None or last_count_at >= last_movement_at)
        )

        if quantity == 0 and not counted_since_movement:
            return "OUT_OF_STOCK", "HIGH"

        if (
            latest_scan
            and latest_scan.status == "DISCREPANCY"
            and (last_movement_at is None or last_movement_at < last_count_at)
            and last_count_at < now - timedelta(days=1)
        ):
            return "DISCREPANCY", "HIGH"

        if quantity <= product.reorder_level and not counted_since_movement:
            return "LOW_STOCK", "MEDIUM"

        if last_count_at is None:
            created = _utc(product.created_at) or now
            if created < now - timedelta(days=1):
                return "NEVER_COUNTED", "LOW"
            return None

        interval = max(int(product.count_interval_days or 30), 1)
        if last_count_at < now - timedelta(days=interval):
            return "OVERDUE_COUNT", "LOW"

        return None

    @staticmethod
    def run(max_new=None, actor=None):
        """Scan all products and create the missing check tasks. Returns a summary."""

        max_new = max_new or current_app.config.get("ALERT_MAX_TASKS_PER_RUN", 25)

        latest_scan_ids = (
            db.session.query(func.max(StockVerification.id))
            .filter(StockVerification.product_id.isnot(None))
            .group_by(StockVerification.product_id)
        )
        latest_scans = {
            s.product_id: s
            for s in StockVerification.query.filter(StockVerification.id.in_(latest_scan_ids))
        }
        last_movements = dict(
            db.session.query(StockMovement.product_id, func.max(StockMovement.created_at))
            .group_by(StockMovement.product_id)
            .all()
        )
        open_products = {
            row[0] for row in db.session.query(CheckTask.product_id)
            .filter(CheckTask.status.in_(["OPEN", "IN_PROGRESS"]))
        }

        rows = (
            db.session.query(Product, Inventory)
            .outerjoin(Inventory, Inventory.product_id == Product.id)
            .filter(Product.is_active.is_(True))
            .all()
        )

        # Max-heap so the most urgent checks are created first.
        heap = StockPriorityHeap()
        candidates = {}

        for product, inventory in rows:
            if product.id in open_products:
                continue

            result = CheckService.evaluate_product(
                product, inventory, latest_scans.get(product.id), last_movements.get(product.id)
            )

            if result:
                reason, priority = result
                candidates[product.id] = (product, reason, priority)
                heap.add(PRIORITY_SCORE[priority], product.id)

        created = []

        while heap.size() and len(created) < max_new:
            product_id = heap.get_highest_priority()["product_id"]
            product, reason, priority = candidates[product_id]
            created.append(CheckService.create_task(product, reason, priority, admin_email=False))

        overdue = CheckService.notify_overdue()

        if created:
            high = sum(1 for t in created if t.priority == "HIGH")
            NotificationService.notify_roles(
                ("manager", "admin"),
                f"{len(created)} new stock check{'' if len(created) == 1 else 's'} created",
                f"{high} high priority. Staff have been notified.",
                category="CHECK_SUMMARY",
                link="/checks",
            )
            log_action(
                actor.id if actor else None, "CHECKS_GENERATED", "CheckTask", None,
                f"{len(created)} task(s) created automatically.",
            )

            # One digest e-mail to the admin instead of one mail per task.
            sections = "\n\n".join(
                f"Job {n}\n" + "\n".join("  " + line for line in CheckService.describe_assignment(t).splitlines())
                for n, t in enumerate(created, start=1)
            )
            NotificationService.email_admin(
                f"{len(created)} new job{'' if len(created) == 1 else 's'} assigned",
                f"The automatic stock scan assigned these checks:\n\n{sections}",
                link="/checks",
            )

        db.session.commit()

        return {
            "created": len(created),
            "overdue_notified": overdue,
            "skipped_with_open_task": len(open_products),
            "remaining_candidates": heap.size(),
        }

    @staticmethod
    def notify_overdue():

        tasks = CheckTask.query.filter(
            CheckTask.status.in_(["OPEN", "IN_PROGRESS"]),
            CheckTask.overdue_notified.is_(False),
        ).all()

        count = 0

        for task in tasks:
            if not task.is_overdue:
                continue

            task.overdue_notified = True
            count += 1

            if task.assignee:
                NotificationService.notify(
                    task.assignee,
                    f"Overdue: count {task.product.name}",
                    "This stock check is past its due time. Please count it as soon as possible.",
                    category="CHECK_OVERDUE",
                    link=f"/scanner?barcode={task.product.barcode}&task={task.id}",
                    email=True,
                )

            CheckService.email_admin_assignment(task, heading="Job overdue")

            NotificationService.notify_roles(
                ("manager", "admin"),
                f"Overdue check: {task.product.name}",
                f"Assigned to {task.assignee.username if task.assignee else 'nobody'}.",
                category="CHECK_OVERDUE",
                link="/checks",
            )

        return count

    # -------------------------------------------------------------
    # Event hooks (called inside other services before their commit)
    # -------------------------------------------------------------

    @staticmethod
    def on_stock_changed(product, new_quantity):
        """Ask for a shelf check as soon as stock drops to the reorder level."""

        if new_quantity > product.reorder_level or CheckService.open_task_for(product.id):
            return None

        reason, priority = ("OUT_OF_STOCK", "HIGH") if new_quantity == 0 else ("LOW_STOCK", "MEDIUM")
        return CheckService.create_task(product, reason, priority)

    @staticmethod
    def on_verified(product, verification, user_id):
        """Close open checks for this product and alert managers about discrepancies."""

        tasks = CheckTask.query.filter(
            CheckTask.product_id == product.id,
            CheckTask.status.in_(["OPEN", "IN_PROGRESS"]),
        ).all()

        for task in tasks:
            task.status = "DONE"
            task.completed_by = user_id
            task.completed_at = _now()
            task.verification_id = verification.id
            task.result_status = verification.status

        if verification.status == "DISCREPANCY":
            diff = verification.discrepancy
            NotificationService.notify_roles(
                ("manager", "admin"),
                f"Discrepancy on {product.name}",
                f"Counted {verification.physical_quantity}, system shows "
                f"{verification.expected_quantity} ({'+' if diff > 0 else ''}{diff}). "
                f"{verification.risk_level.capitalize()} risk.",
                category="DISCREPANCY",
                link="/reports#discrepancies",
                exclude_user_id=user_id,
            )

        return tasks
