"""
migrate_marketplace.py — Add marketplace columns to existing tables.
Run once on production: python migrate_marketplace.py

Safe to re-run — each ALTER is wrapped in a duplicate-column guard.
"""
import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'), override=True)

from app import create_app
from app.extensions import db

app = create_app('production')

ALTERS = [
    # ── experiences ──────────────────────────────────────────────────
    ("experiences", "provider_id",
     "ALTER TABLE experiences ADD COLUMN provider_id VARCHAR(9) NULL"),

    ("experiences", "short_description",
     "ALTER TABLE experiences ADD COLUMN short_description VARCHAR(200) NULL"),

    ("experiences", "inclusions",
     "ALTER TABLE experiences ADD COLUMN inclusions TEXT NULL"),

    ("experiences", "what_to_bring",
     "ALTER TABLE experiences ADD COLUMN what_to_bring TEXT NULL"),

    ("experiences", "cancellation_policy",
     "ALTER TABLE experiences ADD COLUMN cancellation_policy VARCHAR(20) NULL"),

    ("experiences", "listing_status",
     "ALTER TABLE experiences ADD COLUMN listing_status ENUM('draft','pending_review','active') "
     "NOT NULL DEFAULT 'active'"),

    # ── bookings ─────────────────────────────────────────────────────
    ("bookings", "platform_fee_amount",
     "ALTER TABLE bookings ADD COLUMN platform_fee_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00"),

    ("bookings", "provider_amount",
     "ALTER TABLE bookings ADD COLUMN provider_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00"),
]

FK = ("experiences", "fk_experiences_provider_id",
      "ALTER TABLE experiences ADD CONSTRAINT fk_experiences_provider_id "
      "FOREIGN KEY (provider_id) REFERENCES providers(provider_id) ON DELETE SET NULL")


with app.app_context():
    with db.engine.connect() as conn:

        # New tables first (providers, provider_verification_docs, provider_payouts)
        db.create_all()
        print("✓ New tables created (providers, provider_verification_docs, provider_payouts)")

        # ALTER TABLE for existing tables
        for table, col, sql in ALTERS:
            try:
                conn.execute(db.text(sql))
                conn.commit()
                print(f"✓ {table}.{col} added")
            except Exception as e:
                if 'Duplicate column' in str(e) or '1060' in str(e):
                    print(f"  {table}.{col} already exists — skipping")
                else:
                    print(f"  ERROR on {table}.{col}: {e}")

        # FK constraint (skip if already exists)
        try:
            conn.execute(db.text(FK[2]))
            conn.commit()
            print(f"✓ FK {FK[1]} added")
        except Exception as e:
            if '1826' in str(e) or 'Duplicate' in str(e) or 'already exists' in str(e.args[0] if e.args else ''):
                print(f"  FK {FK[1]} already exists — skipping")
            else:
                print(f"  FK skipped (non-critical): {e}")

    print("\nMigration complete.")
