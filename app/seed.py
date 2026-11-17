"""Seed helpers used by `flask seed-demo`, `flask create-admin`, seed_demo.py and seed_admin.py."""

import getpass
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.extensions import db
from app.models.user import User
from app.models.supplier import Supplier
from app.models.product import Product
from app.models.inventory import Inventory, StockMovement, StockVerification


DEMO_USERS = [
    ("admin", "admin@stockflow.local", "admin", "Admin@123456"),
    ("manager", "manager@stockflow.local", "manager", "Manager@123456"),
    ("staff", "staff@stockflow.local", "staff", "Staff@123456"),
]

DEMO_SUPPLIERS = [
    ("TechSource Distributors", "Ravi Kumar", "sales@techsource.example", "+91 98400 11111", "Chennai, Tamil Nadu"),
    ("OfficeMart Supplies", "Priya Nair", "orders@officemart.example", "+91 80 4123 4567", "Bengaluru, Karnataka"),
    ("Hosur Hardware Co.", "Senthil M", "contact@hosurhw.example", "+91 94430 22222", "Hosur, Tamil Nadu"),
]

# sku, barcode, name, category, price, reorder, qty, supplier index
DEMO_PRODUCTS = [
    ("ELEC-001", "8901001000011", "Wireless Mouse", "Electronics", "549.00", 10, 42, 0),
    ("ELEC-002", "8901001000028", "USB Keyboard", "Electronics", "799.00", 8, 6, 0),
    ("ELEC-003", "8901001000035", "24-inch Monitor", "Electronics", "11499.00", 3, 5, 0),
    ("ELEC-004", "8901001000042", "HDMI Cable 1.5m", "Electronics", "249.00", 15, 0, 0),
    ("ELEC-005", "8901001000059", "USB-C Charger 65W", "Electronics", "1899.00", 6, 14, 0),
    ("OFF-001", "8902002000014", "A4 Paper Ream (500)", "Stationery", "320.00", 20, 75, 1),
    ("OFF-002", "8902002000021", "Ball Pen Box (10)", "Stationery", "90.00", 25, 18, 1),
    ("OFF-003", "8902002000038", "Stapler", "Stationery", "185.00", 5, 12, 1),
    ("OFF-004", "8902002000045", "Whiteboard Marker Set", "Stationery", "240.00", 10, 9, 1),
    ("HW-001", "8903003000017", "Screwdriver Set", "Hardware", "650.00", 4, 11, 2),
    ("HW-002", "8903003000024", "Measuring Tape 5m", "Hardware", "210.00", 6, 3, 2),
    ("HW-003", "8903003000031", "Extension Board 4-way", "Hardware", "499.00", 8, 22, 2),
]


def ensure_demo_users():

    created = []

    for username, email, role, password in DEMO_USERS:

        if User.query.filter((User.username == username) | (User.email == email)).first():
            continue

        user = User(username=username, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        created.append(username)

    db.session.commit()

    return created


def seed_demo_data():
    """Idempotent: running twice does not duplicate data."""

    created_users = ensure_demo_users()
    admin = User.query.filter_by(role="admin").first()

    suppliers = []

    for name, contact, email, phone, address in DEMO_SUPPLIERS:

        supplier = Supplier.query.filter_by(email=email).first()

        if not supplier:
            supplier = Supplier(
                company_name=name, contact_person=contact,
                email=email, phone=phone, address=address,
            )
            db.session.add(supplier)

        suppliers.append(supplier)

    db.session.flush()

    new_products = 0
    rng = random.Random(42)
    now = datetime.now(timezone.utc)
    admin_id = admin.id if admin else None
    staff_user = User.query.filter_by(role="staff").first()

    for index, (sku, barcode, name, category, price, reorder, qty, sup) in enumerate(DEMO_PRODUCTS):

        if Product.query.filter((Product.sku == sku) | (Product.barcode == barcode)).first():
            continue

        product = Product(
            sku=sku, barcode=barcode, name=name, category=category,
            unit_price=Decimal(price), reorder_level=reorder,
            supplier_id=suppliers[sup].id,
            description=f"Demo product: {name}",
            count_interval_days=14 if category == "Electronics" else 30,
            created_at=now - timedelta(days=45),
        )
        db.session.add(product)
        db.session.flush()
        db.session.add(Inventory(product_id=product.id, quantity=qty))

        # A few deliveries and sales over the last two weeks, ending exactly on
        # the target quantity, so the dashboard chart has realistic data.
        events = []
        for _ in range(rng.randint(3, 6)):
            when = now - timedelta(days=rng.randint(1, 13), hours=rng.randint(0, 8))
            if rng.random() < .35:
                events.append(["STOCK_IN", rng.randint(4, 12), when, "Supplier delivery (demo)"])
            else:
                events.append(["STOCK_OUT", rng.randint(1, 6), when, "Sales (demo)"])
        events.sort(key=lambda ev: ev[2])

        net = sum(a if k == "STOCK_IN" else -a for k, a, _, _ in events)
        running, lowest = 0, 0
        for k, a, _, _ in events:
            running += a if k == "STOCK_IN" else -a
            lowest = min(lowest, running)

        opening = max(qty - net, -lowest + 2, 5)
        extra = opening + net - qty            # > 0 means we must sell a bit more
        if extra > 0:
            events.append(["STOCK_OUT", extra, now - timedelta(hours=rng.randint(2, 20)), "Sales (demo)"])

        events.insert(0, ["STOCK_IN", opening, now - timedelta(days=20), "Opening stock (demo)"])

        history = []
        current = 0
        for kind, amount, when, note in events:
            new = current + amount if kind == "STOCK_IN" else current - amount
            history.append((kind, amount, current, new, when, note))
            current = new
        assert current == qty, (sku, current, qty)

        for n, (kind, amount, before, after, when, note) in enumerate(history):
            db.session.add(StockMovement(
                product_id=product.id, user_id=admin_id,
                movement_type=kind, quantity=amount,
                previous_quantity=before, new_quantity=after,
                notes=note, created_at=when,
                reference_number=f"{'PO' if kind == 'STOCK_IN' else 'INV'}-{1000 + product.id * 10 + n}",
            ))

        # Shelf counts: most products counted recently, a few never or long ago,
        # and one with a mismatch so every kind of stock check shows up.
        counted_by = staff_user.id if staff_user else admin_id

        if sku not in ("OFF-004", "ELEC-005"):        # these two were never counted
            if sku == "OFF-003":
                db.session.add(StockVerification(
                    product_id=product.id, user_id=counted_by, barcode=barcode,
                    expected_quantity=qty, physical_quantity=qty - 3, discrepancy=-3,
                    risk_score=30, risk_level="LOW", status="DISCREPANCY",
                    created_at=now - timedelta(days=2),
                ))
            else:
                days_ago = 40 if sku == "HW-003" else rng.randint(0, 6)
                db.session.add(StockVerification(
                    product_id=product.id, user_id=counted_by, barcode=barcode,
                    expected_quantity=qty, physical_quantity=qty, discrepancy=0,
                    risk_score=0, risk_level="LOW", status="MATCH",
                    created_at=now - timedelta(days=days_ago),
                ))

        new_products += 1

    db.session.commit()

    # Create the first round of stock checks and notifications.
    from app.services.check_service import CheckService
    checks = CheckService.run() if new_products else {"created": 0}

    lines = [f"Demo data ready. New products: {new_products}. Stock checks created: {checks['created']}."]

    if created_users:
        lines.append("Demo logins created:")
        for username, _, role, password in DEMO_USERS:
            if username in created_users:
                lines.append(f"  {role:<8} username: {username:<8} password: {password}")
    else:
        lines.append("Demo users already existed (see README for credentials).")

    return "\n".join(lines)


def create_admin_interactive():

    username = input("Admin username: ").strip()
    email = input("Admin email: ").strip().lower()
    password = getpass.getpass("Admin password (min 12 chars): ")

    if not username or not email or len(password) < 12:
        raise SystemExit("Enter a username, email and password of at least 12 characters.")

    if User.query.filter((User.username == username) | (User.email == email)).first():
        raise SystemExit("Username or email already exists.")

    admin = User(username=username, email=email, role="admin")
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()

    print("Admin account created successfully.")
