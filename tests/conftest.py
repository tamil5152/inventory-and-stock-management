import pytest

from app import create_app
from app.extensions import db
from app.models.user import User
from config import TestConfig


@pytest.fixture()
def app():

    app = create_app(TestConfig)

    with app.app_context():
        for username, role in (("admin", "admin"), ("manager", "manager"), ("staff", "staff")):
            user = User(username=username, email=f"{username}@test.local", role=role)
            user.set_password("Password123!")
            db.session.add(user)

        db.session.commit()

    # Yield outside an app context so each request gets a fresh `g`.
    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()


def _login(app, username):

    client = app.test_client()
    response = client.post(
        "/login",
        data={"username": username, "password": "Password123!"},
    )
    assert response.status_code == 302
    return client


@pytest.fixture()
def admin(app):
    return _login(app, "admin")


@pytest.fixture()
def manager(app):
    return _login(app, "manager")


@pytest.fixture()
def staff(app):
    return _login(app, "staff")


@pytest.fixture()
def product(admin):

    response = admin.post("/api/products/", json={
        "sku": "elec-001",
        "barcode": "8901001000011",
        "name": "Wireless Mouse",
        "category": "Electronics",
        "unit_price": "549.50",
        "reorder_level": 5,
        "quantity": 20,
    })
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]
