import pytest

from app.extensions import db
from app.models.alerts import CheckTask
from app.models.user import User
from app.services.notification_service import NotificationService

ADMIN_MAIL = "t2064585@gmail.com"


@pytest.fixture()
def mail(app):
    """Turn e-mail on (messages go to NotificationService.outbox in tests)."""
    app.config.update(MAIL_SERVER="smtp.test", MAIL_FROM="stockflow@test.local", ADMIN_EMAIL=ADMIN_MAIL)
    NotificationService.outbox.clear()
    yield NotificationService.outbox
    NotificationService.outbox.clear()


def _shelf(client, code="A1", name="Keyboards & Mice", staff_ids=None):
    r = client.post("/api/shelves/", json={"code": code, "name": name, "location": "Aisle A", "staff_ids": staff_ids or []})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]


def _staff(client, username, shelf_ids, email=None):
    r = client.post("/api/users/", json={
        "username": username, "full_name": username.title() + " Kumar",
        "email": email or f"{username}@shop.in", "phone": "+91 98765 4321" + str(len(username) % 10),
        "role": "staff", "password": "longpassword", "shelf_ids": shelf_ids,
    })
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]


def _to(mail):
    return [m["To"] for m in mail]


def test_create_staff_requires_name_email_mobile(admin):
    base = {"username": "ravi", "full_name": "Ravi K", "email": "ravi@shop.in", "phone": "9876543210", "password": "longpassword"}

    for field, bad in (("full_name", ""), ("full_name", "R4vi<script>"), ("email", "not-an-email"),
                       ("phone", "12345"), ("phone", "98765abcde"), ("shelf_ids", [999])):
        r = admin.post("/api/users/", json={**base, field: bad})
        assert r.status_code == 400, (field, bad, r.get_json())

    r = admin.post("/api/users/", json={**base, "phone": "+91 98765-43210"})
    assert r.status_code == 201
    data = r.get_json()["data"]
    assert data["phone"] == "+919876543210"
    assert data["full_name"] == "Ravi K"
    assert "password_hash" not in data


def test_only_admin_manages_staff_and_managers_manage_shelves(manager, staff):
    assert manager.post("/api/users/", json={}).status_code == 403
    assert staff.post("/api/shelves/", json={"code": "Z1", "name": "X"}).status_code == 403
    assert manager.post("/api/shelves/", json={"code": "Z1", "name": "Spare"}).status_code == 201
    assert manager.post("/api/shelves/", json={"code": "z1", "name": "Dup"}).status_code == 409
    assert manager.post("/api/shelves/", json={"code": "bad code!", "name": "X"}).status_code == 400


def test_new_staff_gets_welcome_mail_and_admin_copy(admin, mail):
    shelf = _shelf(admin)
    _staff(admin, "ravi", [shelf["id"]], email="ravi@shop.in")

    assert "ravi@shop.in" in _to(mail)
    assert ADMIN_MAIL in _to(mail)
    welcome = next(m for m in mail if m["To"] == "ravi@shop.in")
    body = welcome.get_content()
    assert "A1 Keyboards & Mice" in body
    assert "longpassword" not in body          # passwords are never e-mailed


def test_check_goes_to_shelf_staff_and_admin_is_mailed(app, admin, mail):
    a1 = _shelf(admin, "A1", "Keyboards & Mice")
    b1 = _shelf(admin, "B1", "Cables")
    _staff(admin, "ravi", [a1["id"]])
    priya = _staff(admin, "priya", [b1["id"]])

    r = admin.post("/api/products/", json={
        "sku": "CAB-001", "barcode": "8901001000042", "name": "HDMI Cable", "category": "Cables & Adapters",
        "unit_price": 249, "reorder_level": 5, "quantity": 10, "shelf_id": b1["id"],
    })
    assert r.get_json()["data"]["shelf_code"] == "B1"
    mail.clear()

    admin.post("/api/inventory/stock-out", json={"product_id": r.get_json()["data"]["id"], "quantity": 6})

    with app.app_context():
        task = CheckTask.query.one()
        assert task.assigned_to == priya["id"]

    assert "priya@shop.in" in _to(mail)
    admin_mail = next(m for m in mail if m["To"] == ADMIN_MAIL)
    body = admin_mail.get_content()
    assert "Priya Kumar" in body and "priya@shop.in" in body and "Mobile:" in body and "B1 Cables" in body


def test_falls_back_to_any_staff_when_shelf_has_nobody(app, admin, staff, product):
    a1 = _shelf(admin)
    admin.put(f"/api/products/{product['id']}", json={"shelf_id": a1["id"]})
    admin.post("/api/inventory/stock-out", json={"product_id": product["id"], "quantity": 16})

    with app.app_context():
        assert CheckTask.query.one().assignee.username == "staff"


def test_scan_sends_one_digest_to_admin(app, admin, mail, product):
    from datetime import datetime, timedelta, timezone
    from app.models.product import Product
    from app.services.check_service import CheckService

    with app.app_context():
        p = db.session.get(Product, product["id"])
        p.created_at = datetime.now(timezone.utc) - timedelta(days=5)
        db.session.commit()
        mail.clear()
        CheckService.run()

    assert _to(mail).count(ADMIN_MAIL) == 1
    assert "new job assigned" in next(m for m in mail if m["To"] == ADMIN_MAIL)["Subject"]


def test_reassign_notifies_new_person_and_admin(app, admin, mail, product):
    shelf = _shelf(admin)
    ravi = _staff(admin, "ravi", [shelf["id"]])
    task_id = admin.post("/api/checks/", json={"product_id": product["id"]}).get_json()["data"]["id"]
    mail.clear()

    r = admin.put(f"/api/checks/{task_id}", json={"assigned_to": ravi["id"]})
    assert r.get_json()["data"]["assignee_phone"]
    assert "ravi@shop.in" in _to(mail) and ADMIN_MAIL in _to(mail)


def test_adding_shelf_to_staff_notifies_them(app, admin, mail):
    shelf = _shelf(admin)
    ravi = _staff(admin, "ravi", [])
    mail.clear()

    assert admin.put(f"/api/users/{ravi['id']}", json={"shelf_ids": [shelf["id"]]}).status_code == 200
    assert "ravi@shop.in" in _to(mail)

    with app.app_context():
        assert [s.code for s in db.session.get(User, ravi["id"]).shelves] == ["A1"]


def test_test_email_endpoint(admin, staff, app, mail):
    assert staff.post("/api/users/test-email").status_code == 403
    r = admin.post("/api/users/test-email", json={})
    assert r.status_code == 200
    assert mail[-1]["To"] == ADMIN_MAIL

    app.config["MAIL_SERVER"] = ""
    r = admin.post("/api/users/test-email", json={})
    assert r.status_code == 400 and "not set up" in r.get_json()["error"]


def test_old_database_gets_new_columns(tmp_path):
    import sqlite3
    from app import create_app
    from config import TestConfig

    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(80), email VARCHAR(120),
            password_hash VARCHAR(255), role VARCHAR(20), is_active_user BOOLEAN, created_at DATETIME);
        CREATE TABLE products (id INTEGER PRIMARY KEY, sku VARCHAR(50), barcode VARCHAR(100), name VARCHAR(150),
            category VARCHAR(100), description TEXT, unit_price NUMERIC, reorder_level INTEGER,
            supplier_id INTEGER, is_active BOOLEAN, created_at DATETIME, updated_at DATETIME);
    """)
    con.close()

    class OldDb(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{path}"

    create_app(OldDb)
    con = sqlite3.connect(path)
    user_cols = {r[1] for r in con.execute("PRAGMA table_info(users)")}
    product_cols = {r[1] for r in con.execute("PRAGMA table_info(products)")}
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()

    assert {"full_name", "phone"} <= user_cols
    assert {"shelf_id", "count_interval_days"} <= product_cols
    assert {"shelves", "user_shelves", "check_tasks", "notifications"} <= tables
