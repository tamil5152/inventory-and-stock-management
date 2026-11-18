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


# username, full name, e-mail, mobile, role, password, shelf codes
DEMO_USERS = [
    ("admin", "Tamil Selvan", "admin@stockflow.local", "+919384515257", "admin", "Admin@123456", []),
    ("manager", "Meena Raj", "manager@stockflow.local", "+919876500001", "manager", "Manager@123456", []),
    ("staff", "Karthik Kumar", "karthik@stockflow.local", "+919876500002", "staff", "Staff@123456", ["A1", "A2"]),
    ("priya", "Priya Nair", "priya@stockflow.local", "+919876500003", "staff", "Staff@123456", ["B1", "B2"]),
    ("arun", "Arun Prakash", "arun@stockflow.local", "+919876500004", "staff", "Staff@123456", ["C1", "C2"]),
]

# code, name, location
DEMO_SHELVES = [
    ("A1", "Keyboards & Mice", "Aisle A, left rack"),
    ("A2", "Monitors", "Aisle A, floor stack"),
    ("B1", "Cables & Adapters", "Aisle B, pegboard"),
    ("B2", "Storage", "Aisle B, glass cabinet"),
    ("C1", "Audio", "Aisle C, top rack"),
    ("C2", "Networking & Power", "Aisle C, bottom rack"),
]

DEMO_SUPPLIERS = [
    ("TechSource Distributors", "Ravi Kumar", "sales@techsource.example", "+91 98400 11111", "Chennai, Tamil Nadu"),
    ("PeriPro Electronics", "Priya Nair", "orders@peripro.example", "+91 80 4123 4567", "Bengaluru, Karnataka"),
    ("Hosur Computer World", "Senthil M", "contact@hosurcw.example", "+91 94430 22222", "Hosur, Tamil Nadu"),
]

# sku, barcode, name, category, price, reorder, qty, supplier index, shelf code
DEMO_PRODUCTS = [
    ("KBM-001", "8901001000011", "Wireless Mouse", "Keyboards & Mice", "549.00", 10, 42, 0, "A1"),
    ("KBM-002", "8901001000028", "USB Keyboard", "Keyboards & Mice", "799.00", 8, 6, 0, "A1"),
    ("KBM-003", "8901001000097", "Mechanical Gaming Keyboard", "Keyboards & Mice", "3499.00", 4, 9, 1, "A1"),
    ("MON-001", "8901001000035", "24-inch IPS Monitor", "Monitors", "11499.00", 3, 5, 1, "A2"),
    ("MON-002", "8901001000103", "Monitor Arm (Single)", "Monitors", "1899.00", 3, 7, 1, "A2"),
    ("CAB-001", "8901001000042", "HDMI Cable 1.5m", "Cables & Adapters", "249.00", 15, 0, 0, "B1"),
    ("CAB-002", "8902002000014", "USB-C to HDMI Adapter", "Cables & Adapters", "899.00", 6, 18, 2, "B1"),
    ("CAB-003", "8902002000021", "USB 3.0 Hub 4-Port", "Cables & Adapters", "699.00", 8, 4, 2, "B1"),
    ("STO-001", "8902002000038", "1TB External SSD", "Storage", "6499.00", 4, 11, 1, "B2"),
    ("STO-002", "8902002000045", "64GB Pen Drive", "Storage", "449.00", 20, 9, 2, "B2"),
    ("AUD-001", "8903003000017", "USB Headset with Mic", "Audio", "1299.00", 5, 14, 1, "C1"),
    ("AUD-002", "8903003000024", "Bluetooth Speaker", "Audio", "1799.00", 4, 3, 1, "C1"),
    ("NET-001", "8903003000031", "Wi-Fi Router AC1200", "Networking", "2299.00", 3, 8, 0, "C2"),
    ("PWR-001", "8901001000059", "65W USB-C Laptop Charger", "Power & Charging", "1899.00", 6, 14, 0, "C2"),
    ("LAP-001", "8901001000066", "Laptop Cooling Pad", "Laptop Accessories", "999.00", 5, 12, 2, None),
]

def ensure_demo_users():

    created = []

    from flask import current_app
    from app.models.shelf import Shelf

    admin_email = (current_app.config.get("ADMIN_EMAIL") or "").strip().lower()

    for username, full_name, email, phone, role, password, shelf_codes in DEMO_USERS:

        if role == "admin" and admin_email:
            email = admin_email

        if User.query.filter((User.username == username) | (User.email == email)).first():
            continue

        user = User(username=username, email=email, role=role, full_name=full_name, phone=phone)
        user.set_password(password)
        user.shelves = Shelf.query.filter(Shelf.code.in_(shelf_codes)).all() if shelf_codes else []
        db.session.add(user)
        created.append(username)

    db.session.commit()

    return created


def seed_demo_data():
    """Idempotent: running twice does not duplicate data."""

    from app.models.shelf import Shelf

    for code, name, location in DEMO_SHELVES:
        if not Shelf.query.filter_by(code=code).first():
            db.session.add(Shelf(code=code, name=name, location=location))
    db.session.flush()

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

    shelves = {s.code: s for s in Shelf.query.all()}

    for index, (sku, barcode, name, category, price, reorder, qty, sup, shelf_code) in enumerate(DEMO_PRODUCTS):

        if Product.query.filter((Product.sku == sku) | (Product.barcode == barcode)).first():
            continue

        product = Product(
            sku=sku, barcode=barcode, name=name, category=category,
            unit_price=Decimal(price), reorder_level=reorder,
            supplier_id=suppliers[sup].id,
            shelf_id=shelves[shelf_code].id if shelf_code else None,
            description=f"Demo product: {name}",
            count_interval_days=14 if category in ("Storage", "Monitors") else 30,
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
        shelf = shelves.get(shelf_code) if shelf_code else None
        shelf_staff = [u for u in (shelf.staff if shelf else []) if u.role == "staff"]
        counted_by = shelf_staff[0].id if shelf_staff else (staff_user.id if staff_user else admin_id)

        if sku not in ("STO-002", "LAP-001"):        # these two were never counted
            if sku == "CAB-002":
                db.session.add(StockVerification(
                    product_id=product.id, user_id=counted_by, barcode=barcode,
                    expected_quantity=qty, physical_quantity=qty - 3, discrepancy=-3,
                    risk_score=30, risk_level="LOW", status="DISCREPANCY",
                    created_at=now - timedelta(days=2),
                ))
            else:
                days_ago = 40 if sku == "NET-001" else rng.randint(0, 6)
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
        for username, full_name, email, _, role, password, shelf_codes in DEMO_USERS:
            if username in created_users:
                shelves_text = f"  shelves {', '.join(shelf_codes)}" if shelf_codes else ""
                lines.append(f"  {role:<8} {full_name:<14} username: {username:<8} password: {password}{shelves_text}")
    else:
        lines.append("Demo users already existed (see README for credentials).")

    return "\n".join(lines)


def create_admin_interactive():

    from flask import current_app
    from app.utils.validators import validate_email, validate_full_name, validate_phone

    default_email = (current_app.config.get("ADMIN_EMAIL") or "").strip()

    username = input("Admin username: ").strip()
    full_name = input("Full name: ").strip()
    email = input(f"Admin email [{default_email}]: ").strip().lower() or default_email
    phone = input("Mobile number: ").strip()
    password = getpass.getpass("Admin password (min 12 chars): ")

    try:
        full_name = validate_full_name(full_name)
        email = validate_email(email)
        phone = validate_phone(phone)
    except ValueError as error:
        raise SystemExit(str(error))

    if not username or len(password) < 12:
        raise SystemExit("Enter a username and a password of at least 12 characters.")

    if User.query.filter((User.username == username) | (User.email == email)).first():
        raise SystemExit("Username or email already exists.")

    admin = User(username=username, email=email, role="admin", full_name=full_name, phone=phone)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()

    print("Admin account created successfully.")
