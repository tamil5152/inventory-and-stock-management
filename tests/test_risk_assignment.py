from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.models.alerts import CheckTask
from app.models.inventory import StockVerification
from app.models.product import Product
from app.models.user import User
from app.services.assignment_service import ProductRisk, StaffSelector
from app.services.check_service import CheckService
from app.services.notification_service import NotificationService

ADMIN_MAIL = "t2064585@gmail.com"


@pytest.fixture()
def mail(app):
    app.config.update(MAIL_SERVER="smtp.test", MAIL_FROM="stockflow@test.local", ADMIN_EMAIL=ADMIN_MAIL)
    NotificationService.outbox.clear()
    yield NotificationService.outbox
    NotificationService.outbox.clear()


@pytest.fixture()
def team(app, admin):
    """Shelf A1 with two staff members: ravi and priya."""
    shelf = admin.post("/api/shelves/", json={"code": "A1", "name": "Keyboards"}).get_json()["data"]
    people = {}
    for name in ("ravi", "priya"):
        r = admin.post("/api/users/", json={
            "username": name, "full_name": name.title() + " K", "email": f"{name}@shop.in",
            "phone": "+919876543210", "password": "longpassword", "shelf_ids": [shelf["id"]],
        })
        people[name] = r.get_json()["data"]["id"]
    return {"shelf": shelf["id"], **people}


def _product(admin, shelf_id, sku="KBM-001", barcode="8901001000011", qty=20, price=549, reorder=5):
    r = admin.post("/api/products/", json={
        "sku": sku, "barcode": barcode, "name": f"Item {sku}", "category": "Keyboards & Mice",
        "unit_price": price, "reorder_level": reorder, "quantity": qty, "shelf_id": shelf_id,
    })
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]


def _login(app, username):
    client = app.test_client()
    assert client.post("/login", data={"username": username, "password": "longpassword"}).status_code == 302
    return client


def _record_counts(app, username, matches, mismatches):
    with app.app_context():
        user = User.query.filter_by(username=username).one()
        for i in range(matches + mismatches):
            ok = i < matches
            db.session.add(StockVerification(
                user_id=user.id, barcode="X", expected_quantity=10, physical_quantity=10 if ok else 7,
                discrepancy=0 if ok else -3, status="MATCH" if ok else "DISCREPANCY",
            ))
        db.session.commit()


# ---------------- Risk score ----------------

def test_risk_score_explains_itself(app, admin, team):
    p = _product(admin, team["shelf"], qty=0, price=11499)

    with app.app_context():
        risk = ProductRisk.compute(db.session.get(Product, p["id"]))

    assert risk["level"] in ("MEDIUM", "HIGH")
    assert "out of stock" in risk["factors"]
    assert any("never physically counted" in f for f in risk["factors"])


def test_high_value_fast_seller_scores_higher(app, admin, team):
    slow = _product(admin, team["shelf"], sku="SLOW-01", barcode="11111111", qty=30, price=100)
    fast = _product(admin, team["shelf"], sku="FAST-01", barcode="22222222", qty=30, price=2000)
    admin.post("/api/inventory/stock-out", json={"product_id": fast["id"], "quantity": 24})  # 6 left of a fast seller

    with app.app_context():
        r_slow = ProductRisk.compute(db.session.get(Product, slow["id"]))
        r_fast = ProductRisk.compute(db.session.get(Product, fast["id"]))

    assert r_fast["score"] > r_slow["score"]
    assert any("selling fast" in f or "days of stock left" in f for f in r_fast["factors"])


# ---------------- Assignment ----------------

def test_high_risk_job_goes_to_most_accurate_counter(app, admin, team):
    _record_counts(app, "ravi", matches=4, mismatches=6)     # 40% accurate
    _record_counts(app, "priya", matches=10, mismatches=0)   # 100% accurate
    p = _product(admin, team["shelf"], qty=10)

    admin.post("/api/inventory/stock-out", json={"product_id": p["id"], "quantity": 10})  # out of stock

    with app.app_context():
        task = CheckTask.query.one()
        assert task.assignee.username == "priya"
        assert task.priority == "HIGH"
        assert "looks after shelf A1" in task.assignment_reason
        assert "count accuracy" in task.assignment_reason


def test_workload_is_spread_across_the_shelf_team(app, admin, team):
    for i in range(4):
        p = _product(admin, team["shelf"], sku=f"S{i}", barcode=f"9000000{i}", qty=10)
        admin.post("/api/inventory/stock-out", json={"product_id": p["id"], "quantity": 8})

    with app.app_context():
        owners = [t.assignee.username for t in CheckTask.query.all()]

    assert owners.count("ravi") == 2 and owners.count("priya") == 2


def test_risk_threshold_creates_high_risk_checks(app, admin, team):
    p = _product(admin, team["shelf"], qty=40, price=900, reorder=5)   # Rs. 36,000 of stock

    with app.app_context():
        product = db.session.get(Product, p["id"])
        product.created_at = datetime.now(timezone.utc) - timedelta(days=60)
        db.session.add(StockVerification(
            product_id=product.id, barcode=product.barcode, expected_quantity=40, physical_quantity=40,
            discrepancy=0, status="MATCH", created_at=datetime.now(timezone.utc) - timedelta(days=90),
        ))
        db.session.commit()

        app.config["ALERT_RISK_THRESHOLD"] = 25
        CheckService.run()
        task = CheckTask.query.one()
        assert task.reason in ("OVERDUE_COUNT", "HIGH_RISK")
        assert task.risk_score >= 25
        assert "high stock value" in task.risk_factors


# ---------------- Mismatch → recount by a second person ----------------

def test_mismatch_triggers_recount_by_someone_else_then_escalates(app, admin, team, mail):
    p = _product(admin, team["shelf"], qty=20)
    ravi = _login(app, "ravi")

    r = ravi.post("/api/scanning/verify", json={"barcode": p["barcode"], "physical_quantity": 15})
    assert r.get_json()["status"] == "DISCREPANCY"

    with app.app_context():
        recount = CheckTask.query.filter_by(status="OPEN").one()
        assert recount.reason == "RECOUNT"
        assert recount.priority == "HIGH"
        assert recount.assignee.username == "priya"
        assert "second opinion" in recount.assignment_reason

    assert "priya@shop.in" in [m["To"] for m in mail]
    priya_mail = next(m for m in mail if m["To"] == "priya@shop.in")
    assert priya_mail["Subject"].startswith("[StockFlow] Urgent job")
    assert "Risk:" in priya_mail.get_content() and "Chosen because:" in priya_mail.get_content()
    mail.clear()

    priya = _login(app, "priya")
    r = priya.post("/api/scanning/verify", json={"barcode": p["barcode"], "physical_quantity": 15})
    assert r.get_json()["completed_checks"] == 1

    with app.app_context():
        assert CheckTask.query.filter(CheckTask.status.in_(["OPEN", "IN_PROGRESS"])).count() == 0

    escalation = [m for m in mail if m["To"] == ADMIN_MAIL]
    assert escalation and "Recount confirms mismatch" in escalation[0]["Subject"]


# ---------------- Overdue → automatic reassignment ----------------

def test_overdue_high_priority_job_moves_to_next_best_person(app, admin, team, mail):
    p = _product(admin, team["shelf"], qty=10)
    admin.post("/api/inventory/stock-out", json={"product_id": p["id"], "quantity": 10})

    with app.app_context():
        task = CheckTask.query.one()
        first = task.assignee.username
        task.due_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.session.commit()
        mail.clear()

        assert CheckService.notify_overdue() == 1
        db.session.commit()

        task = CheckTask.query.one()
        second = task.assignee.username
        assert second != first
        assert task.reassign_count == 1
        assert not task.is_overdue
        assert "reassigned automatically" in task.assignment_reason

    recipients = [m["To"] for m in mail]
    assert f"{second}@shop.in" in recipients      # new person told
    assert f"{first}@shop.in" in recipients       # previous person told
    assert ADMIN_MAIL in recipients               # admin copy

    # A second miss is not bounced around again; it is reported as overdue.
    with app.app_context():
        task = CheckTask.query.one()
        task.due_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.session.commit()
        CheckService.notify_overdue()
        db.session.commit()
        assert CheckTask.query.one().assignee.username == second


def test_checks_api_exposes_risk_and_reason(admin, team, app):
    p = _product(admin, team["shelf"], qty=10)
    admin.post("/api/inventory/stock-out", json={"product_id": p["id"], "quantity": 8})

    task = admin.get("/api/checks/").get_json()["data"][0]
    assert task["risk_score"] is not None
    assert task["risk_level"] in ("LOW", "MEDIUM", "HIGH")
    assert task["risk_factors"]
    assert "looks after shelf A1" in task["assignment_reason"]


def test_accuracy_prior_for_new_staff(app, team):
    with app.app_context():
        stats = StaffSelector.accuracy([team["ravi"]])
        assert stats[team["ravi"]] == (0.9, 0)
