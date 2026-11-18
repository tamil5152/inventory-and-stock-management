"""
Risk-based stock-check assignment.

ProductRisk scores how urgently a product needs a physical count (0-100) and
explains why. StaffSelector picks the best person for the job:

  1. People responsible for the product's shelf come first. If nobody looks
     after the shelf, any active staff member is considered, then managers.
  2. Among them, the cost of giving the job to someone is
         risk-weighted workload  +  (1 - count accuracy) x job risk x 2
     so busy people get fewer jobs, and high-risk jobs go to the people whose
     counts are most often correct.
  3. A recount after a mismatch never goes back to the person who made the
     mismatching count when someone else is available (a second opinion).
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func

from app.extensions import db
from app.models.alerts import CheckTask
from app.models.inventory import Inventory, StockMovement, StockVerification
from app.models.user import User

VELOCITY_DAYS = 14
ACCURACY_DAYS = 60
DEFAULT_TASK_RISK = 50


def _utc(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _now():
    return datetime.now(timezone.utc)


def level_for(score):
    if score >= 70:
        return "HIGH"
    if score >= 40:
        return "MEDIUM"
    return "LOW"


PRIORITY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def higher_priority(a, b):
    return a if PRIORITY_RANK[a] >= PRIORITY_RANK[b] else b


class ProductRisk:
    """Risk that the shelf does not match the system, and the cost if it doesn't."""

    @staticmethod
    def sales_velocity(product_ids=None):
        """Average units sold per day over the last VELOCITY_DAYS days, per product."""

        since = _now() - timedelta(days=VELOCITY_DAYS)
        query = (
            db.session.query(StockMovement.product_id, func.sum(StockMovement.quantity))
            .filter(StockMovement.movement_type == "STOCK_OUT", StockMovement.created_at >= since)
        )
        if product_ids is not None:
            query = query.filter(StockMovement.product_id.in_(product_ids))

        return {pid: (total or 0) / VELOCITY_DAYS for pid, total in query.group_by(StockMovement.product_id)}

    @staticmethod
    def context_for(product):
        """Load everything compute() needs for a single product."""

        inventory = Inventory.query.filter_by(product_id=product.id).first()
        latest_scan = (
            StockVerification.query.filter_by(product_id=product.id)
            .order_by(StockVerification.id.desc()).first()
        )
        last_movement_at = (
            db.session.query(func.max(StockMovement.created_at))
            .filter(StockMovement.product_id == product.id).scalar()
        )
        velocity = ProductRisk.sales_velocity([product.id]).get(product.id, 0)

        return inventory, latest_scan, last_movement_at, velocity

    @staticmethod
    def compute(product, inventory=None, latest_scan=None, last_movement_at=None, velocity=None):
        """Return {"score": 0-100, "level": LOW|MEDIUM|HIGH, "factors": [str, ...]}."""

        if inventory is None and latest_scan is None and last_movement_at is None and velocity is None:
            inventory, latest_scan, last_movement_at, velocity = ProductRisk.context_for(product)

        now = _now()
        quantity = inventory.quantity if inventory else 0
        reorder = max(int(product.reorder_level or 0), 0)
        velocity = velocity or 0
        score = 0.0
        factors = []

        # 1. Stock level (max 40)
        if quantity == 0:
            score += 40
            factors.append("out of stock")
        elif quantity <= reorder:
            score += 20 + 15 * (1 - quantity / max(reorder, 1))
            factors.append(f"only {quantity} left (reorder at {reorder})")

        # 2. Selling fast: days of stock left (max 20)
        if quantity > 0 and velocity > 0:
            days_left = quantity / velocity
            if days_left < 3:
                score += 20
                factors.append(f"selling fast, about {days_left:.0f} day{'s' if round(days_left) != 1 else ''} of stock left")
            elif days_left < 7:
                score += 10
                factors.append(f"about {days_left:.0f} days of stock left")

        # 3. Unresolved count mismatch (max 30)
        last_count_at = _utc(latest_scan.created_at) if latest_scan else None
        last_movement_at = _utc(last_movement_at)

        if latest_scan is not None and latest_scan.status == "DISCREPANCY":
            fixed_since = last_movement_at is not None and last_movement_at > last_count_at
            if not fixed_since:
                expected = max(latest_scan.expected_quantity or 0, 1)
                size = min(abs(latest_scan.discrepancy or 0) / expected, 1)
                score += 15 + 15 * size
                factors.append(f"last count was off by {abs(latest_scan.discrepancy or 0)}")

        # 4. Count cycle (max 20)
        interval = max(int(product.count_interval_days or 30), 1)
        if last_count_at is None:
            score += 15
            factors.append("never physically counted")
        else:
            age_days = (now - last_count_at).total_seconds() / 86400
            if age_days > interval:
                score += 10 + min(10, (age_days - interval) / interval * 10)
                factors.append(f"last counted {age_days:.0f} days ago (cycle {interval} days)")

        # 5. Money at stake (max 10)
        stock_value = quantity * float(product.unit_price or 0)
        if stock_value >= 20000:
            score += 10
            factors.append(f"high stock value (Rs. {stock_value:,.0f})")
        elif stock_value >= 5000:
            score += 5
            factors.append(f"stock value Rs. {stock_value:,.0f}")

        score = round(min(score, 100), 1)

        return {"score": score, "level": level_for(score), "factors": factors}


class StaffSelector:

    @staticmethod
    def accuracy(user_ids):
        """Share of each person's counts in the last ACCURACY_DAYS days that matched.

        Uses a prior of 9 matches in 10 counts so new staff start at 90%.
        Returns {user_id: (accuracy 0-1, number_of_counts)}.
        """

        since = _now() - timedelta(days=ACCURACY_DAYS)
        rows = (
            db.session.query(
                StockVerification.user_id,
                func.count(StockVerification.id),
                func.sum(case((StockVerification.status == "MATCH", 1), else_=0)),
            )
            .filter(StockVerification.user_id.in_(user_ids), StockVerification.created_at >= since)
            .group_by(StockVerification.user_id)
            .all()
        )
        stats = {uid: ((int(matches or 0) + 9) / (total + 10), total) for uid, total, matches in rows}

        return {uid: stats.get(uid, (0.9, 0)) for uid in user_ids}

    @staticmethod
    def workload(user_ids):
        """Risk-weighted open work: sum of the risk scores of each person's open checks."""

        rows = (
            db.session.query(
                CheckTask.assigned_to,
                func.count(CheckTask.id),
                func.sum(func.coalesce(CheckTask.risk_score, DEFAULT_TASK_RISK)),
            )
            .filter(CheckTask.assigned_to.in_(user_ids), CheckTask.status.in_(["OPEN", "IN_PROGRESS"]))
            .group_by(CheckTask.assigned_to)
            .all()
        )
        stats = {uid: (count, float(points or 0)) for uid, count, points in rows}

        return {uid: stats.get(uid, (0, 0.0)) for uid in user_ids}

    @staticmethod
    def candidate_pool(product):
        """(people, why) for the first non-empty group: shelf staff, shelf managers, all staff, managers, admins."""

        shelf = product.shelf if product is not None else None

        if shelf is not None and shelf.is_active:
            people = shelf.active_staff()
            for roles in (("staff",), ("manager", "admin")):
                group = [u for u in people if u.role in roles]
                if group:
                    return group, f"looks after shelf {shelf.code}"

            no_shelf_note = f"nobody looks after shelf {shelf.code}, so chosen from all staff"
        else:
            no_shelf_note = "product has no shelf, so chosen from all staff"

        for roles, label in ((("staff",), "all staff"), (("manager",), "managers"), (("admin",), "admins")):
            group = User.query.filter(User.role.in_(roles), User.is_active_user.is_(True)).all()
            if group:
                note = no_shelf_note if roles == ("staff",) else f"no staff available, so chosen from {label}"
                return group, note

        return [], "no active users"

    @staticmethod
    def choose(product, risk_score, exclude_ids=()):
        """Return (user or None, list of human-readable reasons)."""

        pool, pool_reason = StaffSelector.candidate_pool(product)
        exclude_ids = {i for i in exclude_ids if i}
        reasons = []

        if exclude_ids:
            others = [u for u in pool if u.id not in exclude_ids]

            if others:
                pool = others
                reasons.append("second opinion: did not make the last count")
            else:
                # Look wider (staff first, then managers) before giving it back to the same person.
                for roles in (("staff",), ("manager",)):
                    wider = User.query.filter(
                        User.role.in_(roles), User.is_active_user.is_(True), User.id.notin_(exclude_ids),
                    ).all()
                    if wider:
                        pool = wider
                        pool_reason = "second opinion from another " + ("staff member" if roles == ("staff",) else "manager")
                        break

        if not pool:
            return None, ["no active staff to assign"]

        ids = [u.id for u in pool]
        accuracy = StaffSelector.accuracy(ids)
        load = StaffSelector.workload(ids)
        weight = max(float(risk_score or 0), 10) / 100

        def cost(user):
            acc, _ = accuracy[user.id]
            _, points = load[user.id]
            return (points + (1 - acc) * 200 * weight, user.id)

        best = min(pool, key=cost)
        acc, counts = accuracy[best.id]
        open_jobs, _ = load[best.id]

        reasons.insert(0, pool_reason)
        reasons.append(f"{acc:.0%} count accuracy" + (f" over {counts} counts" if counts else " (new counter)"))
        reasons.append("no other open jobs" if open_jobs == 0 else f"{open_jobs} other open job{'s' if open_jobs != 1 else ''}")

        if len(pool) > 1:
            reasons.append(f"best of {len(pool)} people")

        return best, reasons
