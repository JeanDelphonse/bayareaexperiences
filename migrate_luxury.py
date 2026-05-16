"""
Migration: Luxury tier columns — BAE-PRD-LUXURY-v1.0
Run once: python migrate_luxury.py

Adds to the experiences table:
  - is_premium              BOOLEAN NOT NULL DEFAULT FALSE
  - luxury_vehicle_type     ENUM (6 values) NULL
  - luxury_vehicle_custom   VARCHAR(150) NULL
  - driver_notes            TEXT NULL

Non-breaking: existing rows get is_premium=FALSE and NULL vehicle columns.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from app.extensions import db


def run():
    app = create_app()
    with app.app_context():
        engine = db.engine
        dialect = engine.dialect.name  # 'sqlite' or 'mysql'

        with engine.connect() as conn:
            if dialect == 'sqlite':
                _migrate_sqlite(conn)
            else:
                _migrate_mysql(conn)

        print("Migration complete.")


def _migrate_sqlite(conn):
    from sqlalchemy import text

    # SQLite doesn't support ENUM — use TEXT with a CHECK constraint
    stmts = [
        "ALTER TABLE experiences ADD COLUMN is_premium BOOLEAN NOT NULL DEFAULT 0",
        "ALTER TABLE experiences ADD COLUMN luxury_vehicle_type TEXT CHECK(luxury_vehicle_type IN "
        "('cadillac_escalade','lincoln_navigator','mercedes_sprinter','mercedes_s_class','bmw_7_series','luxury_suv_custom')) NULL",
        "ALTER TABLE experiences ADD COLUMN luxury_vehicle_custom VARCHAR(150) NULL",
        "ALTER TABLE experiences ADD COLUMN driver_notes TEXT NULL",
    ]
    for stmt in stmts:
        try:
            conn.execute(text(stmt))
            print(f"  OK: {stmt[:70]}...")
        except Exception as e:
            if 'duplicate column' in str(e).lower():
                print(f"  SKIP (already exists): {stmt[:50]}...")
            else:
                raise
    conn.commit()


def _migrate_mysql(conn):
    from sqlalchemy import text, inspect as sa_inspect

    inspector = sa_inspect(conn)
    existing  = {col['name'] for col in inspector.get_columns('experiences')}

    additions = []
    if 'is_premium' not in existing:
        additions.append("ADD COLUMN is_premium BOOLEAN NOT NULL DEFAULT FALSE")
    if 'luxury_vehicle_type' not in existing:
        additions.append(
            "ADD COLUMN luxury_vehicle_type ENUM("
            "'cadillac_escalade','lincoln_navigator','mercedes_sprinter',"
            "'mercedes_s_class','bmw_7_series','luxury_suv_custom') NULL"
        )
    if 'luxury_vehicle_custom' not in existing:
        additions.append("ADD COLUMN luxury_vehicle_custom VARCHAR(150) NULL")
    if 'driver_notes' not in existing:
        additions.append("ADD COLUMN driver_notes TEXT NULL")

    if not additions:
        print("  All columns already exist — nothing to do.")
        return

    stmt = "ALTER TABLE experiences " + ", ".join(additions)
    conn.execute(text(stmt))
    conn.commit()
    print(f"  Added: {', '.join(c.split(' ')[2] for c in additions)}")


if __name__ == '__main__':
    run()
