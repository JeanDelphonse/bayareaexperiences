"""
Add pagination performance indexes to all 6 admin listing tables.
Safe to run multiple times — uses IF NOT EXISTS (requires MySQL 8.0+ / SQLite 3.x).

Usage:
    python migrate_pagination_indexes.py
"""
from app import create_app
from app.extensions import db

INDEXES = [
    # bookings
    "CREATE INDEX IF NOT EXISTS ix_booking_created_at     ON booking (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_booking_booking_status ON booking (booking_status)",
    "CREATE INDEX IF NOT EXISTS ix_booking_experience_id  ON booking (experience_id)",
    "CREATE INDEX IF NOT EXISTS ix_booking_staff_id       ON booking (staff_id)",
    "CREATE INDEX IF NOT EXISTS ix_booking_user_id        ON booking (user_id)",
    # experiences
    "CREATE INDEX IF NOT EXISTS ix_experience_sort_order  ON experience (sort_order)",
    "CREATE INDEX IF NOT EXISTS ix_experience_is_active   ON experience (is_active)",
    # timeslots
    "CREATE INDEX IF NOT EXISTS ix_timeslot_slot_date     ON timeslot (slot_date)",
    "CREATE INDEX IF NOT EXISTS ix_timeslot_experience_id ON timeslot (experience_id)",
    # staff_members
    "CREATE INDEX IF NOT EXISTS ix_staff_member_full_name ON staff_member (full_name)",
    "CREATE INDEX IF NOT EXISTS ix_staff_member_is_active ON staff_member (is_active)",
    # contact_submissions
    "CREATE INDEX IF NOT EXISTS ix_contact_submission_created_at ON contact_submission (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_contact_submission_is_read    ON contact_submission (is_read)",
    # chat_sessions
    "CREATE INDEX IF NOT EXISTS ix_chat_session_started_at    ON chat_session (started_at)",
    "CREATE INDEX IF NOT EXISTS ix_chat_session_user_id       ON chat_session (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_chat_session_was_escalated ON chat_session (was_escalated)",
]


if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        with db.engine.connect() as conn:
            for sql in INDEXES:
                try:
                    conn.execute(db.text(sql))
                    print(f'OK   {sql}')
                except Exception as exc:
                    print(f'SKIP {sql}\n     {exc}')
            conn.commit()
    print('\nDone.')
