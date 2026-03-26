"""
migrate_pickup_cities.py — Add expanded pickup cities to all active experiences.
Run once on production: python migrate_pickup_cities.py

Safe to re-run — skips cities that already exist for each experience.
"""
import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'), override=True)

from app import create_app
from app.extensions import db
from app.models import Experience, ExperiencePickupLocation
from app.utils import generate_pk

app = create_app('production')

NEW_CITIES = [
    'Cupertino, CA',
    'Fremont, CA',
    'Los Gatos, CA',
    'Menlo Park, CA',
    'Monterey, CA',
    'Mountain View, CA',
    'Palo Alto, CA',
    'Redwood City, CA',
    'San Francisco, CA',
    'San Jose, CA',
    'Santa Clara, CA',
    'Santa Cruz, CA',
    'Sunnyvale, CA',
]

with app.app_context():
    experiences = Experience.query.filter_by(is_active=True).all()
    added = 0
    skipped = 0

    for exp in experiences:
        existing = {loc.pickup_city for loc in exp.pickup_locations}
        for city in NEW_CITIES:
            if city in existing:
                skipped += 1
            else:
                loc = ExperiencePickupLocation(
                    id            = generate_pk(),
                    experience_id = exp.experience_id,
                    pickup_city   = city,
                )
                db.session.add(loc)
                added += 1

    db.session.commit()
    print(f'Done. {added} cities added, {skipped} already existed.')
