"""
migrate_staff.py — BAE-PRD-STAFF-v1.0 database migration

Run once:
    python migrate_staff.py

Safe to re-run — each ALTER TABLE is wrapped in a try/except for duplicate column errors.
New tables are created via db.create_all() which is a no-op if the table already exists.
"""
import pymysql
pymysql.install_as_MySQLdb()

from app import create_app
from app.extensions import db
from sqlalchemy import text


def column_exists(conn, table, column):
    result = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = :table AND COLUMN_NAME = :col"
    ), {'table': table, 'col': column})
    return result.scalar() > 0


def add_column_if_missing(conn, table, column, definition):
    if not column_exists(conn, table, column):
        conn.execute(text(f'ALTER TABLE `{table}` ADD COLUMN `{column}` {definition}'))
        print(f'  + {table}.{column}')
    else:
        print(f'  . {table}.{column} already exists — skipped')


app = create_app('production')

with app.app_context():
    with db.engine.begin() as conn:
        print('=== staff_members — adding portal columns ===')
        add_column_if_missing(conn, 'staff_members', 'user_id',
                              'CHAR(9) NULL DEFAULT NULL REFERENCES users(user_id)')
        add_column_if_missing(conn, 'staff_members', 'staff_portal_token',
                              'CHAR(64) NULL DEFAULT NULL')
        add_column_if_missing(conn, 'staff_members', 'staff_portal_token_expires',
                              'DATETIME NULL DEFAULT NULL')

        print('\n=== bookings — adding provider_staff_id ===')
        add_column_if_missing(conn, 'bookings', 'provider_staff_id',
                              'CHAR(9) NULL DEFAULT NULL')

    # Create new tables (no-op if they already exist)
    print('\n=== creating new tables ===')
    # Import models so SQLAlchemy knows about them
    from app.models import ProviderStaffMember, StaffAssignmentLog  # noqa
    db.create_all()
    print('  provider_staff_members — ok')
    print('  staff_assignment_log   — ok')

    # Add FK constraint on bookings.provider_staff_id if not already present
    # (SQLite doesn't enforce FKs strictly; MySQL/prod handles this)
    with db.engine.begin() as conn:
        try:
            conn.execute(text(
                'ALTER TABLE `bookings` ADD CONSTRAINT `fk_bookings_provider_staff_id` '
                'FOREIGN KEY (`provider_staff_id`) '
                'REFERENCES `provider_staff_members`(`provider_staff_id`)'
            ))
            print('\n  + FK bookings.provider_staff_id added')
        except Exception as e:
            if 'Duplicate' in str(e) or 'already exists' in str(e) or '1826' in str(e) or '1005' in str(e):
                print('\n  . FK bookings.provider_staff_id already exists — skipped')
            else:
                print(f'\n  ! FK warning (non-fatal): {e}')

print('\nMigration complete.')
