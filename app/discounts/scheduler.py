"""Nightly discount expiry — run every 30 min via cron."""
from datetime import datetime


def expire_ended_discounts() -> int:
    """Deactivates any experience discount whose discount_end has passed."""
    from app.models import Experience
    from app.extensions import db

    now = datetime.utcnow()
    expired = Experience.query.filter(
        Experience.discount_active == True,   # noqa: E712
        Experience.discount_end != None,      # noqa: E711
        Experience.discount_end <= now,
    ).all()

    for exp in expired:
        exp.discount_active = False

    if expired:
        db.session.commit()

    return len(expired)


def run():
    """Entry point for cron: python -c 'from app.discounts.scheduler import run; run()'"""
    from app import create_app
    app = create_app()
    with app.app_context():
        count = expire_ended_discounts()
        print(f'Expired {count} discount(s).')
