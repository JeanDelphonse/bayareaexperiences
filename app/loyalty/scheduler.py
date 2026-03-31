"""Nightly VIP expiry job — run via cron: python -c 'from app.loyalty.scheduler import run; run()'"""
import logging
import os
from datetime import datetime, timezone, timedelta

log = logging.getLogger('loyalty')

REMINDER_DAYS = int(os.environ.get('VIP_EXPIRY_REMINDER_DAYS', 30))


def process_vip_expiry():
    """
    1. Expire VIP records past their 12-month window.
    2. Send 30-day expiry reminders (once per VIP record).
    """
    from app.models import VipCustomer, DiscountCode
    from app.extensions import db

    now               = datetime.now(timezone.utc)
    reminder_deadline = now + timedelta(days=REMINDER_DAYS)

    # Expire overdue active records
    expired = VipCustomer.query.filter(
        VipCustomer.status == 'active',
        VipCustomer.discount_expires_at <= now,
    ).all()
    for vip in expired:
        vip.status = 'expired'
        code = DiscountCode.query.get(vip.discount_code_id)
        if code:
            code.is_active = False
        log.info(f'VIP expired: vip_id={vip.vip_id} user={vip.user_id}')

    # Send 30-day reminders (only once)
    expiring_soon = VipCustomer.query.filter(
        VipCustomer.status == 'active',
        VipCustomer.discount_expires_at <= reminder_deadline,
        VipCustomer.notification_sent_at == None,  # noqa: E711
    ).all()
    for vip in expiring_soon:
        try:
            from app.loyalty.email import send_vip_expiry_reminder
            send_vip_expiry_reminder(vip.user, vip)
            vip.notification_sent_at = now
            log.info(f'VIP expiry reminder sent: vip_id={vip.vip_id}')
        except Exception as e:
            log.error(f'Expiry reminder failed for vip {vip.vip_id}: {e}')

    db.session.commit()


def run():
    """Entry point for cron execution."""
    from app import create_app
    app = create_app()
    with app.app_context():
        process_vip_expiry()
