"""Adds columns introduced in newer versions to an existing database.

db.create_all() creates missing tables but never alters existing ones, so a
database created by an older version of StockFlow would miss new columns.
"""

from sqlalchemy import inspect, text

from app.extensions import db

NEW_COLUMNS = {
    "products": {
        "count_interval_days": "INTEGER NOT NULL DEFAULT 30",
    },
}


def upgrade_schema():

    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())

    with db.engine.begin() as connection:
        for table, columns in NEW_COLUMNS.items():
            if table not in tables:
                continue

            existing = {c["name"] for c in inspector.get_columns(table)}

            for name, ddl in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
