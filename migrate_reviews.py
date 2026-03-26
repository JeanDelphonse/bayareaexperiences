"""
migrate_reviews.py — Add reviews system tables and columns.
Run once on production: python migrate_reviews.py

Safe to re-run — new tables are created via db.create_all() (idempotent),
and each ALTER is wrapped in a duplicate-column guard.
"""
import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'), override=True)

from app import create_app
from app.extensions import db

app = create_app('production')

# Columns to add to the existing experiences table
ALTERS = [
    ("experiences", "avg_star_rating",
     "ALTER TABLE experiences ADD COLUMN avg_star_rating DECIMAL(3,2) NULL DEFAULT NULL"),

    ("experiences", "review_count",
     "ALTER TABLE experiences ADD COLUMN review_count INT NOT NULL DEFAULT 0"),
]

with app.app_context():
    with db.engine.connect() as conn:

        # Create all new tables:
        #   experience_reviews, review_tokens, review_votes, review_flags
        db.create_all()
        print("✓ New tables created (experience_reviews, review_tokens, review_votes, review_flags)")

        # ALTER existing experiences table
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

        print("\nDone. Reviews migration complete.")
