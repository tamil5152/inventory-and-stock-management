"""
Physical stock-check alerts.

Scans the catalogue and creates CheckTask records asking staff to physically
count a product when:
  * stock is zero or at/below the reorder level and nobody has counted it since
    the last stock movement,
  * the latest count found a discrepancy that was never resolved (no adjustment
    and no clean recount for a day),
  * the product has never been counted, or its count cycle has expired.

  * its risk score (see assignment_service.ProductRisk) reaches ALERT_RISK_THRESHOLD,
  * a count did not match: a recount goes straight to a second person.

Every check carries a 0-100 risk score that sets its priority and due time,
and is assigned by StaffSelector (shelf team first, then accuracy and
risk-weighted workload). The assignee gets an in-app notification and an
e-mail, and the admin mailbox (ADMIN_EMAIL) gets a copy. Overdue high-priority
checks are handed to the next best person automatically.
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
from app.services.assignment_service import ProductRisk, StaffSelector, higher_priority, level_for
from app.services.notification_service import NotificationService
from app.utils.audit import log_action
from app.utils.dsa import StockPriorityHeap


PRIORITY_SCORE = {"HIGH": 90, "MEDIUM": 60, "LOW": 30}
DUE_HOURS = {"HIGH": 8, "MEDIUM": 24, "LOW": 72}
REASON_PRIORITY = {
    "OUT_OF_STOCK": "HIGH", "DISCREPANCY": "HIGH", "RECOUNT": "HIGH",
    "LOW_STOCK": "MEDIUM", "HIGH_RISK": "MEDIUM",
    "NEVER_COUNTED": "LOW", "OVERDUE_COUNT": "LOW", "MANUAL": "MEDIUM",
}


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
    def pick_assignee(product=None, risk_score=50, exclude_ids=()):
        """Best person for the job and the reasons (see StaffSelector)."""

        return StaffSelector.choose(product, risk_score, exclude_ids)

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
            f"Risk:      {task.risk_score:.0f}/100 ({level_for(task.risk_score).lower()})" if task.risk_score is not None else "Risk:      -",
            f"Priority:  {task.priority.capitalize()}",
            f"Due:       {_local(task.due_at)}",
        ]

        if task.risk_factors:
            lines.append(f"Why:       {task.risk_factors}")

        if person:
            lines += [
                "",
                f"Assigned to: {person.display_name}",
                f"E-mail:      {person.email}",
                f"Mobile:      {person.phone or 'Not given'}",
            ]
            if task.assignment_reason:
                lines.append(f"Chosen because: {task.assignment_reason}")
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
    def create_task(product, reason, priority=None, assignee=None, created_by=None, note=None, due_at=None,
                    notify=True, admin_email=True, risk=None, exclude_ids=()):
        """
        Create a check. Priority is the higher of the reason's own priority and the
        risk level. The assignee is chosen automatically unless one is given.
        """

        risk = risk or ProductRisk.compute(product)
        priority = higher_priority(priority or REASON_PRIORITY.get(reason, "MEDIUM"), risk["level"])

        if assignee is None:
            assignee, why = CheckService.pick_assignee(product, risk["score"], exclude_ids)
        else:
            why = ["chosen by " + (created_by.display_name if created_by else "a manager")]

        task = CheckTask(
            product_id=product.id,
            assigned_to=assignee.id if assignee else None,
            created_by=created_by.id if created_by else None,
            reason=reason,
            priority=priority,
            note=(note or "").strip()[:1000] or None,
            due_at=due_at or (_now() + timedelta(hours=DUE_HOURS[priority])),
            risk_score=risk["score"],
            risk_factors="; ".join(risk["factors"])[:2000] or None,
            assignment_reason="; ".join(why)[:1000],
        )
        db.session.add(task)
        db.session.flush()

        if notify and assignee:
            CheckService.notify_assignee(task, intro="You have a new stock check.")

        if notify and admin_email:
            CheckService.email_admin_assignment(task)

        return task

    @staticmethod
    def notify_assignee(task, intro, title_prefix="Count"):
        """In-app notification plus e-mail to the person who must do the count."""

        product = task.product
        person = task.assignee
        shelf_text = f" on shelf {product.shelf.label}" if product.shelf else ""
        link = f"/scanner?barcode={product.barcode}&task={task.id}"
        risk_text = f" Risk {task.risk_score:.0f}/100." if task.risk_score is not None else ""

        NotificationService.notify(
            person,
            f"{title_prefix} {product.name} ({product.sku}){shelf_text}",
            f"{CheckTask.REASONS.get(task.reason, task.reason)}. Priority: {task.priority.lower()}.{risk_text}",
            category="CHECK_ASSIGNED",
            link=link,
        )
        NotificationService.send_email(
            person.email,
            f"{'Urgent job' if task.priority == 'HIGH' else 'New job'}: count {product.name}{shelf_text}",
            f"Hello {person.display_name},\n\n{intro}\n\n"
            f"{CheckService.describe_assignment(task)}\n\n"
            "Open the link, scan the barcode, count the shelf and enter the number.",
            link=link,
        )

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
        velocity = ProductRisk.sales_velocity()
        threshold = float(current_app.config.get("ALERT_RISK_THRESHOLD", 60))
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

            scan = latest_scans.get(product.id)
            moved = last_movements.get(product.id)
            result = CheckService.evaluate_product(product, inventory, scan, moved)
            risk = ProductRisk.compute(product, inventory, scan, moved, velocity.get(product.id, 0))

            if result is None and risk["score"] >= threshold:
                result = ("HIGH_RISK", "MEDIUM")

            if result:
                reason, priority = result
                candidates[product.id] = (product, reason, priority, risk)
                # Most risky first; the reason's priority breaks ties.
                heap.add(risk["score"] + PRIORITY_SCORE[priority] / 1000, product.id)

        created = []

        while heap.size() and len(created) < max_new:
            product_id = heap.get_highest_priority()["product_id"]
            product, reason, priority, risk = candidates[product_id]
            created.append(CheckService.create_task(product, reason, priority, admin_email=False, risk=risk))

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
        """
        Tell people about overdue checks (once per check). Overdue high-priority
        checks are handed to the next best person automatically, one time.
        """

        tasks = CheckTask.query.filter(
            CheckTask.status.in_(["OPEN", "IN_PROGRESS"]),
            CheckTask.overdue_notified.is_(False),
        ).all()

        count = 0
        auto_reassign = current_app.config.get("AUTO_REASSIGN_OVERDUE", True)

        for task in tasks:
            if not task.is_overdue:
                continue

            count += 1
            previous = task.assignee

            if auto_reassign and task.priority == "HIGH" and (task.reassign_count or 0) == 0:
                new_person, why = CheckService.pick_assignee(
                    task.product, task.risk_score or 70, exclude_ids=[task.assigned_to]
                )

                if new_person is not None and new_person.id != task.assigned_to:
                    CheckService._reassign(task, new_person, why, previous)
                    continue

            task.overdue_notified = True

            if previous:
                NotificationService.notify(
                    previous,
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
                f"Assigned to {previous.display_name if previous else 'nobody'}.",
                category="CHECK_OVERDUE",
                link="/checks",
            )

        return count

    @staticmethod
    def _reassign(task, new_person, why, previous):

        task.assigned_to = new_person.id
        task.reassign_count = (task.reassign_count or 0) + 1
        task.status = "OPEN"
        task.overdue_notified = False
        task.due_at = _now() + timedelta(hours=DUE_HOURS[task.priority])
        task.assignment_reason = "; ".join(
            [f"reassigned automatically: {previous.display_name if previous else 'nobody'} did not finish in time"] + why
        )[:1000]
        db.session.flush()
        db.session.refresh(task)

        CheckService.notify_assignee(
            task,
            intro=f"This urgent stock check was moved to you because it was not done in time"
                  f"{' by ' + previous.display_name if previous else ''}.",
            title_prefix="Urgent: count",
        )

        if previous:
            NotificationService.notify(
                previous,
                f"Check moved: {task.product.name}",
                f"It was overdue, so it is now assigned to {new_person.display_name}.",
                category="CHECK_OVERDUE",
                link="/checks",
                email=True,
            )

        NotificationService.notify_roles(
            ("manager", "admin"),
            f"Overdue check moved: {task.product.name}",
            f"From {previous.display_name if previous else 'nobody'} to {new_person.display_name}.",
            category="CHECK_OVERDUE",
            link="/checks",
        )
        CheckService.email_admin_assignment(task, heading="Overdue job reassigned")
        log_action(None, "CHECK_AUTO_REASSIGNED", "CheckTask", task.id,
                   f"{previous.username if previous else '-'} -> {new_person.username}")

    # -------------------------------------------------------------
    # Event hooks (called inside other services before their commit)
    # -------------------------------------------------------------

    @staticmethod
    def on_stock_changed(product, new_quantity):
        """Ask for a shelf check as soon as stock drops to the reorder level."""

        if new_quantity > product.reorder_level or CheckService.open_task_for(product.id):
            return None

        reason = "OUT_OF_STOCK" if new_quantity == 0 else "LOW_STOCK"
        return CheckService.create_task(product, reason)

    @staticmethod
    def on_verified(product, verification, user_id):
        """
        Close open checks for this product. If the count did not match:
          * first mismatch: a recount goes straight to a different person,
          * mismatch on a recount: escalate to managers and the admin mailbox.
        """

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

        if verification.status != "DISCREPANCY":
            return tasks

        diff = verification.discrepancy
        counted = (
            f"Counted {verification.physical_quantity}, system shows "
            f"{verification.expected_quantity} ({'+' if diff > 0 else ''}{diff})."
        )
        was_recount = any(t.reason == "RECOUNT" for t in tasks)

        if was_recount:
            NotificationService.notify_roles(
                ("manager", "admin"),
                f"Recount confirms mismatch on {product.name}",
                f"{counted} Two people have now counted it. Review and adjust the stock.",
                category="DISCREPANCY",
                link=f"/scanner?barcode={product.barcode}",
            )
            NotificationService.email_admin(
                f"Recount confirms mismatch: {product.name}",
                f"A second person counted {product.name} ({product.sku}) and it still does not match.\n\n"
                f"{counted}\n\nPlease check for theft, damage or a recording error and adjust the stock.",
                link="/reports#discrepancies",
            )
            return tasks

        NotificationService.notify_roles(
            ("manager", "admin"),
            f"Discrepancy on {product.name}",
            f"{counted} {verification.risk_level.capitalize()} risk. A recount has been assigned.",
            category="DISCREPANCY",
            link="/checks",
            exclude_user_id=user_id,
        )

        CheckService.create_task(
            product, "RECOUNT", "HIGH",
            note=f"{counted} Please count again carefully.",
            exclude_ids=[user_id],
        )

        return tasks
