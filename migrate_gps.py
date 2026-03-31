"""
migrate_gps.py — One-time migration for GPS tracking feature (BAE-PRD-GPS-v1.0).

Run once on production:
    python migrate_gps.py

Creates:
  - tracking_sessions table
  - tracking_locations table
  - booking_tracking_tokens table
  - bookings.tracking_enabled column
"""
import sys
sys.path.insert(0, '.')
from app import create_app
from app.extensions import db
from sqlalchemy import text, inspect

app = create_app('production')

with app.app_context():
    # Create new tables (safe — skips if already exist)
    db.create_all()
    print('New GPS tables created (or already exist).')

    # Add tracking_enabled to bookings if missing
    insp = inspect(db.engine)
    existing_cols = [c['name'] for c in insp.get_columns('bookings')]
    if 'tracking_enabled' not in existing_cols:
        with db.engine.connect() as conn:
            conn.execute(text(
                'ALTER TABLE bookings ADD COLUMN tracking_enabled BOOLEAN NOT NULL DEFAULT 1'
            ))
            conn.commit()
        print('Added bookings.tracking_enabled column.')
    else:
        print('bookings.tracking_enabled already exists — skipped.')

    print('Migration complete.')
