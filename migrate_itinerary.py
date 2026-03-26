"""
Migration: Add core_stops to experiences + create booking_itineraries table.
Run once: python migrate_itinerary.py
"""
from app import create_app
from app.extensions import db

app = create_app('production')

with app.app_context():
    # Add core_stops column to experiences if not present
    with db.engine.connect() as conn:
        try:
            conn.execute(db.text(
                "ALTER TABLE experiences ADD COLUMN core_stops TEXT NULL"
            ))
            conn.commit()
            print('Added core_stops to experiences.')
        except Exception as e:
            print(f'core_stops column may already exist: {e}')

    # Create booking_itineraries table
    db.create_all()
    print('booking_itineraries table created (if not exists).')
    print('Migration complete.')
