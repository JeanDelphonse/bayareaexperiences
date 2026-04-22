"""
BAE-PRD-PROVIDER-ACCOUNT-v1.0 migration
Adds users.must_change_password column.
Run once: python migrate_provider_account.py
"""
from app import create_app
from app.extensions import db

app = create_app()
with app.app_context():
    with db.engine.connect() as conn:
        from sqlalchemy import text, inspect
        inspector = inspect(db.engine)
        cols = [c['name'] for c in inspector.get_columns('users')]
        if 'must_change_password' not in cols:
            conn.execute(text(
                'ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT FALSE'
            ))
            conn.commit()
            print('Added users.must_change_password')
        else:
            print('users.must_change_password already exists — skipping')
