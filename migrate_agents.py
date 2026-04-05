"""
migrate_agents.py — one-time migration for Agents PRD columns.

Adds to existing tables:
  experiences : is_mystery
  bookings    : mystery_vibe, mystery_reveal_sent_at

New tables (agent_runs, agent_settings, agent_social_posts, agent_ad_copies,
agent_email_campaigns, partners, partner_outreach) are created by db.create_all()
automatically on first app start.

Run once:
    python migrate_agents.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from app.extensions import db
from sqlalchemy import text, inspect as sa_inspect

app = create_app(os.getenv('FLASK_ENV', 'default'))

with app.app_context():
    insp = sa_inspect(db.engine)
    dialect = db.engine.dialect.name   # 'sqlite' or 'mysql'

    # ── experiences: is_mystery ───────────────────────────────────────────────
    ecols = [c['name'] for c in insp.get_columns('experiences')]
    with db.engine.connect() as conn:
        if 'is_mystery' not in ecols:
            conn.execute(text(
                'ALTER TABLE experiences ADD COLUMN is_mystery BOOLEAN NOT NULL DEFAULT 0'
            ))
            print('  + experiences.is_mystery')
        else:
            print('  ~ experiences.is_mystery (already present)')

        # ── bookings: mystery_vibe, mystery_reveal_sent_at ───────────────────
        bcols = [c['name'] for c in insp.get_columns('bookings')]
        if 'mystery_vibe' not in bcols:
            if dialect == 'mysql':
                conn.execute(text(
                    "ALTER TABLE bookings ADD COLUMN mystery_vibe "
                    "ENUM('adventure','foodie','culture','relax','celebrate') NULL"
                ))
            else:
                conn.execute(text(
                    "ALTER TABLE bookings ADD COLUMN mystery_vibe VARCHAR(20) NULL"
                ))
            print('  + bookings.mystery_vibe')
        else:
            print('  ~ bookings.mystery_vibe (already present)')

        if 'mystery_reveal_sent_at' not in bcols:
            conn.execute(text(
                'ALTER TABLE bookings ADD COLUMN mystery_reveal_sent_at DATETIME NULL'
            ))
            print('  + bookings.mystery_reveal_sent_at')
        else:
            print('  ~ bookings.mystery_reveal_sent_at (already present)')

        conn.commit()

    # ── new tables via create_all ─────────────────────────────────────────────
    db.create_all()
    print('  + new agent tables created (if not already present)')

    print('\nAgents migration complete.')
