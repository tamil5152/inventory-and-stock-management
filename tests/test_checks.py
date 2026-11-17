from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.alerts import CheckTask, Notification
from app.models.inventory import StockVerification
from app.models.product import Product
from app.models.user import User
from app.services.check_service import CheckService


def _staff_id(app):
    with app.app_context():
        return User.query.filter_by(username="staff").first().id


def test_stock_out_to_low_level_creates_check_and_notifies_staff(app, staff, product):
    r = staff.post("/api/inventory/stock-out", json={"product_id": product["id"], "quantity": 16})
    assert r.status_code == 200

    tasks = staff.get("/api/checks/").get_json()["data"]
    assert len(tasks) == 1
    assert tasks[0]["reason"] == "LOW_STOCK"
    assert tasks[0]["assignee"] == "staff"

    notes = staff.get("/api/notifications/").get_json()
    assert notes["unread"] >= 1
    assert notes["data"][0]["category"] == "CHECK_ASSIGNED"
    assert "barcode=8901001000011" in notes["data"][0]["link"]


def test_out_of_stock_is_high_priority(staff, product):
    staff.post("/api/inventory/stock-out", json={"product_id": product["id"], "quantity": 20})
    task = staff.get("/api/checks/").get_json()["data"][0]
    assert task["reason"] == "OUT_OF_STOCK"
    assert task["priority"] == "HIGH"


def test_verification_closes_open_check_and_alerts_managers(app, staff, manager, product):
    staff.post("/api/inventory/stock-out", json={"product_id": product["id"], "quantity": 16})
    r = staff.post("/api/scanning/verify", json={"barcode": "8901001000011", "physical_quantity": 3})
    assert r.get_json()["completed_checks"] == 1
    assert staff.get("/api/checks/").get_json()["data"] == []

    done = staff.get("/api/checks/?status=done").get_json()["data"][0]
    assert done["status"] == "DONE"
    assert done["result_status"] == "DISCREPANCY"

    manager_notes = manager.get("/api/notifications/").get_json()["data"]
    assert any(n["category"] == "DISCREPANCY" for n in manager_notes)


def test_scan_generates_never_counted_and_overdue_tasks(app, product):
    with app.app_context():
        p = db.session.get(Product, product["id"])
        p.created_at = datetime.now(timezone.utc) - timedelta(days=5)
        db.session.commit()

        result = CheckService.run()
        assert result["created"] == 1
        task = CheckTask.query.one()
        assert task.reason == "NEVER_COUNTED"

        # Running again must not duplicate.
        assert CheckService.run()["created"] == 0

        # Complete it, make the count old, it becomes overdue on the next cycle.
        task.status = "DONE"
        db.session.add(StockVerification(
            product_id=p.id, barcode=p.barcode, expected_quantity=20,
            physical_quantity=20, discrepancy=0, status="MATCH",
            created_at=datetime.now(timezone.utc) - timedelta(days=40),
        ))
        db.session.commit()

        CheckService.run()
        assert CheckTask.query.filter_by(status="OPEN").one().reason == "OVERDUE_COUNT"


def test_overdue_task_notifies_once(app, staff, product):
    staff.post("/api/inventory/stock-out", json={"product_id": product["id"], "quantity": 16})

    with app.app_context():
        task = CheckTask.query.one()
        task.due_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.session.commit()

        assert CheckService.notify_overdue() == 1
        db.session.commit()
        assert CheckService.notify_overdue() == 0

    categories = [n["category"] for n in staff.get("/api/notifications/").get_json()["data"]]
    assert "CHECK_OVERDUE" in categories


def test_manager_creates_assigns_and_cancels(app, manager, staff, product):
    staff_id = _staff_id(app)
    r = manager.post("/api/checks/", json={
        "product_id": product["id"], "assigned_to": staff_id, "priority": "high", "note": "Shelf B3",
    })
    assert r.status_code == 201
    task_id = r.get_json()["data"]["id"]

    assert manager.post("/api/checks/", json={"product_id": product["id"]}).status_code == 409
    assert staff.post("/api/checks/", json={"product_id": product["id"]}).status_code == 403

    assert staff.post(f"/api/checks/{task_id}/start").get_json()["data"]["status"] == "IN_PROGRESS"
    assert manager.put(f"/api/checks/{task_id}", json={"priority": "LOW"}).status_code == 200
    assert manager.post(f"/api/checks/{task_id}/cancel").status_code == 200
    assert manager.post(f"/api/checks/{task_id}/cancel").status_code == 400


def test_staff_cannot_touch_other_users_task(app, manager, admin, product):
    with app.app_context():
        admin_id = User.query.filter_by(username="admin").first().id

    task_id = manager.post("/api/checks/", json={"product_id": product["id"], "assigned_to": admin_id}).get_json()["data"]["id"]

    client = app.test_client()
    client.post("/login", data={"username": "staff", "password": "Password123!"})
    assert client.post(f"/api/checks/{task_id}/start").status_code == 403
    assert client.get("/api/checks/").get_json()["data"] == []


def test_run_endpoint_and_summary(manager, staff, product):
    assert staff.post("/api/checks/run").status_code == 403
    assert manager.post("/api/checks/run").get_json()["success"] is True
    summary = staff.get("/api/checks/summary").get_json()["data"]
    assert set(summary) >= {"open", "high", "overdue", "mine", "mine_overdue"}


def test_notifications_mark_read(app, staff, product):
    staff.post("/api/inventory/stock-out", json={"product_id": product["id"], "quantity": 16})
    data = staff.get("/api/notifications/").get_json()
    nid = data["data"][0]["id"]

    assert staff.post(f"/api/notifications/{nid}/read").status_code == 200
    assert staff.post("/api/notifications/read-all").status_code == 200
    assert staff.get("/api/notifications/").get_json()["unread"] == 0

    with app.app_context():
        other = Notification.query.filter(Notification.user_id != _staff_id(app)).first()
    if other:
        assert staff.post(f"/api/notifications/{other.id}/read").status_code == 404


def test_charts_endpoint(admin, product):
    data = admin.get("/api/charts").get_json()["data"]
    assert len(data["trend"]) == 14
    assert sum(day["in"] for day in data["trend"]) == 20


def test_count_interval_validation(admin, product):
    assert admin.put(f"/api/products/{product['id']}", json={"count_interval_days": 0}).status_code == 400
    r = admin.put(f"/api/products/{product['id']}", json={"count_interval_days": 7})
    assert r.get_json()["data"]["count_interval_days"] == 7
