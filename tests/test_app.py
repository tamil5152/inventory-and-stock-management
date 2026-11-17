from app.services.risk_service import RiskService


# ---------------- Auth & pages ----------------

def test_login_required_redirects(app):
    client = app.test_client()
    assert client.get("/").status_code == 302
    assert client.get("/api/products/").status_code == 401


def test_bad_login(app):
    client = app.test_client()
    response = client.post("/login", data={"username": "admin", "password": "wrong"})
    assert response.status_code == 200
    assert b"Invalid username or password" in response.data


def test_all_pages_render(admin, product):
    for path in ("/", "/products", "/inventory", "/scanner", "/suppliers", "/reports", "/users"):
        response = admin.get(path)
        assert response.status_code == 200, path


def test_users_page_admin_only(staff):
    assert staff.get("/users").status_code == 403
    assert staff.get("/api/users/").status_code == 403


def test_logout(admin):
    assert admin.post("/logout").status_code == 302
    assert admin.get("/").status_code == 302


# ---------------- Products ----------------

def test_create_product_normalises_and_opening_stock(admin, product):
    assert product["sku"] == "ELEC-001"
    assert product["quantity"] == 20
    history = admin.get(f"/api/inventory/movements?product_id={product['id']}").get_json()["data"]
    assert history[0]["notes"] == "Opening stock"


def test_duplicate_sku_rejected(admin, product):
    response = admin.post("/api/products/", json={
        "sku": "ELEC-001", "barcode": "99999999", "name": "Other", "unit_price": 1,
    })
    assert response.status_code == 409


def test_invalid_price_rejected(admin):
    response = admin.post("/api/products/", json={
        "sku": "X1", "barcode": "12345678", "name": "Bad", "unit_price": "-5",
    })
    assert response.status_code == 400


def test_staff_cannot_create_product(staff):
    response = staff.post("/api/products/", json={
        "sku": "X1", "barcode": "12345678", "name": "Nope", "unit_price": 1,
    })
    assert response.status_code == 403


def test_update_and_archive_product(manager, product):
    response = manager.put(f"/api/products/{product['id']}", json={"name": "Silent Mouse", "reorder_level": 8})
    assert response.status_code == 200
    assert response.get_json()["data"]["name"] == "Silent Mouse"

    assert manager.post(f"/api/products/{product['id']}/archive").status_code == 200
    names = [p["name"] for p in manager.get("/api/products/").get_json()["data"]]
    assert "Silent Mouse" not in names


def test_search_and_lookups(admin, product):
    assert len(admin.get("/api/products/?q=mouse").get_json()["data"]) == 1
    assert admin.get("/api/products/barcode/8901001000011").status_code == 200
    assert admin.get("/api/products/sku/elec-001").status_code == 200
    assert admin.get("/api/products/sku/NOPE").status_code == 404


def test_delete_blocked_with_history(admin, product):
    assert admin.delete(f"/api/products/{product['id']}").status_code == 409


# ---------------- Inventory ----------------

def test_stock_in_and_out(staff, product):
    r = staff.post("/api/inventory/stock-in", json={"product_id": product["id"], "quantity": 5})
    assert r.status_code == 200 and r.get_json()["new_quantity"] == 25

    r = staff.post("/api/inventory/stock-out", json={"product_id": product["id"], "quantity": 22})
    assert r.status_code == 200
    assert r.get_json()["new_quantity"] == 3
    assert r.get_json()["low_stock"] is True


def test_cannot_go_negative(staff, product):
    r = staff.post("/api/inventory/stock-out", json={"product_id": product["id"], "quantity": 999})
    assert r.status_code == 400
    assert "Insufficient" in r.get_json()["error"]


def test_invalid_quantity(staff, product):
    for qty in (0, -1, "abc", 1.5):
        r = staff.post("/api/inventory/stock-in", json={"product_id": product["id"], "quantity": qty})
        assert r.status_code == 400, qty


def test_adjust_permissions(staff, manager, product):
    assert staff.post("/api/inventory/adjust", json={"product_id": product["id"], "quantity": 7}).status_code == 403
    r = manager.post("/api/inventory/adjust", json={"product_id": product["id"], "quantity": 7})
    assert r.status_code == 200
    assert r.get_json()["new_quantity"] == 7


# ---------------- Scanning ----------------

def test_verify_match_and_discrepancy(staff, product):
    r = staff.post("/api/scanning/verify", json={"barcode": "8901001000011", "physical_quantity": 20})
    assert r.get_json()["status"] == "MATCH"

    staff.post("/api/scanning/session/reset")
    r = staff.post("/api/scanning/verify", json={"barcode": "8901001000011", "physical_quantity": 15})
    data = r.get_json()
    assert data["status"] == "DISCREPANCY"
    assert data["discrepancy"] == -5
    assert data["risk"]["score"] > 0


def test_verify_zero_count_allowed(staff, product):
    r = staff.post("/api/scanning/verify", json={"barcode": "8901001000011", "physical_quantity": 0})
    assert r.status_code == 200
    assert r.get_json()["status"] == "DISCREPANCY"


def test_duplicate_scan_detected(staff, product):
    body = {"barcode": "8901001000011", "physical_quantity": 20}
    assert staff.post("/api/scanning/verify", json=body).status_code == 200
    r = staff.post("/api/scanning/verify", json=body)
    assert r.status_code == 409
    assert staff.post("/api/scanning/verify", json={**body, "force": True}).status_code == 200


def test_unknown_barcode_logged(staff):
    r = staff.post("/api/scanning/verify", json={"barcode": "UNKNOWN-1", "physical_quantity": 3})
    assert r.status_code == 200
    assert r.get_json()["status"] == "UNKNOWN_BARCODE"
    history = staff.get("/api/scanning/history?issues=1").get_json()["data"]
    assert history  # discrepancy list shows DISCREPANCY only
    assert staff.get("/api/reports/discrepancies").get_json()["data"][0]["status"] == "UNKNOWN_BARCODE"


def test_batch_scan(staff, product):
    r = staff.post("/api/scanning/batch", json={"scans": [
        {"barcode": "8901001000011", "physical_quantity": 20},
        {"barcode": "8901001000011", "physical_quantity": 20},
    ]})
    statuses = [row["status"] for row in r.get_json()["data"]]
    assert statuses == ["MATCH", "DUPLICATE"]


# ---------------- Suppliers & users ----------------

def test_supplier_crud(manager, staff):
    r = manager.post("/api/suppliers/", json={"company_name": "Acme", "phone": "+91 98765 43210", "email": "a@acme.in"})
    assert r.status_code == 201
    sid = r.get_json()["data"]["id"]

    assert manager.put(f"/api/suppliers/{sid}", json={"contact_person": "Ravi"}).status_code == 200
    assert manager.post(f"/api/suppliers/{sid}/toggle").get_json()["data"]["is_active"] is False
    assert staff.post("/api/suppliers/", json={"company_name": "X", "phone": "9876543210"}).status_code == 403


def test_admin_creates_user(admin, app):
    r = admin.post("/api/users/", json={
        "username": "newbie", "full_name": "New Bie", "email": "n@x.io", "phone": "+91 98765 43210",
        "role": "staff", "password": "longpassword",
    })
    assert r.status_code == 201
    client = app.test_client()
    assert client.post("/login", data={"username": "newbie", "password": "longpassword"}).status_code == 302


def test_admin_cannot_demote_self(admin):
    me = [u for u in admin.get("/api/users/").get_json()["data"] if u["username"] == "admin"][0]
    assert admin.put(f"/api/users/{me['id']}", json={"role": "staff"}).status_code == 400


# ---------------- Reports ----------------

def test_reports_and_exports(admin, product):
    assert admin.get("/api/reports/stock").get_json()["data"][0]["stock_value"] == 20 * 549.5
    assert admin.get("/api/reports/categories").status_code == 200
    assert admin.get("/api/reports/movements?start=2000-01-01&type=STOCK_IN").status_code == 200
    assert admin.get("/api/reports/movements?start=bad").status_code == 400
    assert admin.get("/api/reports/audit").status_code == 200

    csv_response = admin.get("/api/reports/export/stock.csv")
    assert csv_response.mimetype == "text/csv"
    assert b"ELEC-001" in csv_response.data

    pdf = admin.get("/api/reports/export/stock.pdf")
    assert pdf.mimetype == "application/pdf"
    assert pdf.data[:4] == b"%PDF"

    assert admin.get("/api/reports/export/movements.csv").status_code == 200


def test_priority_ranking(admin, product):
    admin.post("/api/inventory/stock-out", json={"product_id": product["id"], "quantity": 18})
    risk = admin.get("/api/reports/risk").get_json()["data"]
    assert risk[0]["sku"] == "ELEC-001"
    assert risk[0]["risk_level"] in ("MEDIUM", "HIGH")


def test_risk_service():
    assert RiskService.calculate(10, 10, 2)["score"] == 0
    assert RiskService.calculate(10, 0, 2)["level"] == "MEDIUM"
    assert RiskService.calculate(0, 5, 0)["score"] == 100
