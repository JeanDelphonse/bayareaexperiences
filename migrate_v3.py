"""
migrate_v3.py — Add referral_source column to bookings table (PRD v3.0)
Run once: python migrate_v3.py
"""
import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'), override=True)

from app import create_app
from app.extensions import db

app = create_app('production')

with app.app_context():
    with db.engine.connect() as conn:
        try:
            conn.execute(db.text(
                "ALTER TABLE bookings ADD COLUMN referral_source VARCHAR(100) NULL"
            ))
            conn.commit()
            print("✓ referral_source column added to bookings table")
        except Exception as e:
            if 'Duplicate column' in str(e) or '1060' in str(e):
                print("✓ referral_source column already exists — skipping")
            else:
                raise
