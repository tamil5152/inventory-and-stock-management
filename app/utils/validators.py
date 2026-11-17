
import re
from decimal import Decimal, InvalidOperation


VALID_ROLES = ("admin", "manager", "staff")

VALID_MOVEMENTS = (
    "STOCK_IN",
    "STOCK_OUT",
    "ADJUSTMENT"
)


def validate_required(value, field_name):

    if value is None or not str(value).strip():
        raise ValueError(f"{field_name} is required.")

    return str(value).strip()


def validate_email(email):

    email = validate_required(email, "Email")

    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

    if not re.match(pattern, email):
        raise ValueError("Invalid email address.")

    return email.lower()


def validate_barcode(barcode):

    barcode = validate_required(barcode, "Barcode")

    if not re.fullmatch(r"[A-Za-z0-9-]{4,100}", barcode):
        raise ValueError("Barcode must contain 4-100 letters, numbers or hyphens.")

    return barcode


def validate_sku(sku):

    sku = validate_required(sku, "SKU")

    if not re.fullmatch(r"[A-Za-z0-9_-]{2,50}", sku):
        raise ValueError("Invalid SKU format.")

    return sku.upper()


def validate_price(price):

    try:
        value = Decimal(str(price))

    except (InvalidOperation, TypeError):
        raise ValueError("Invalid product price.")

    if not value.is_finite() or value < 0 or value.as_tuple().exponent < -2:
        raise ValueError("Price must be non-negative with at most two decimal places.")

    return value


def validate_quantity(quantity):

    if isinstance(quantity, bool):
        raise ValueError("Quantity must be an integer.")

    try:
        value = int(quantity)

    except (ValueError, TypeError):
        raise ValueError("Quantity must be an integer.")

    if str(value) != str(quantity).strip() or value < 0:
        raise ValueError("Quantity cannot be negative.")

    return value


def validate_role(role):

    role = validate_required(role, "Role").lower()

    if role not in VALID_ROLES:
        raise ValueError("Invalid user role.")

    return role


def validate_movement_type(movement_type):

    movement_type = validate_required(
        movement_type,
        "Movement type"
    ).upper()

    if movement_type not in VALID_MOVEMENTS:
        raise ValueError("Invalid stock movement type.")

    return movement_type
