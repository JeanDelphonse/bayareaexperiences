"""Loyalty email notifications."""
import logging
import threading
from flask import current_app

log = logging.getLogger('loyalty')


def _send_async(app, subject, recipients, html, txt=None):
    def _send():
        with app.app_context():
            try:
                from app.extensions import mail
                from app.utils import send_email
                send_email(mail, subject=subject, recipients=recipients,
                           body_html=html, body_text=txt)
            except Exception as e:
                log.error(f'Loyalty email failed to {recipients}: {e}')
    threading.Thread(target=_send, daemon=True).start()


def send_vip_welcome_email(user, vip, discount_code):
    try:
        from flask import render_template
        base_url = current_app.config.get('BASE_URL', 'https://bayareaexperiences.com')
        referral_url = f"{base_url}/r/{vip.referral_code}"
        html = render_template('email/vip_welcome.html',
                               user=user, vip=vip,
                               discount_code=discount_code,
                               referral_url=referral_url)
        _send_async(
            current_app._get_current_object(),
            subject=f"You're a Bay Area Experiences VIP, {user.first_name} \u2b50",
            recipients=[user.email],
            html=html,
        )
    except Exception as e:
        log.error(f'send_vip_welcome_email failed for {user.user_id}: {e}')


def send_referral_credit_notification(referrer, booking, vip):
    try:
        from flask import render_template
        from decimal import Decimal
        html = render_template('email/referral_credit.html',
                               user=referrer, booking=booking, vip=vip,
                               credit_amount=25.00,
                               new_balance=float(referrer.total_referral_credit_balance))
        _send_async(
            current_app._get_current_object(),
            subject=f"{referrer.first_name}, your friend just booked \u2014 $25 credit added \u2713",
            recipients=[referrer.email],
            html=html,
        )
    except Exception as e:
        log.error(f'send_referral_credit_notification failed for {referrer.user_id}: {e}')


def send_vip_expiry_reminder(user, vip):
    try:
        from flask import render_template
        base_url    = current_app.config.get('BASE_URL', 'https://bayareaexperiences.com')
        referral_url = f"{base_url}/r/{vip.referral_code}"
        html = render_template('email/vip_expiry_reminder.html',
                               user=user, vip=vip, referral_url=referral_url)
        _send_async(
            current_app._get_current_object(),
            subject=f"{user.first_name}, your 15% VIP discount expires in 30 days",
            recipients=[user.email],
            html=html,
        )
    except Exception as e:
        log.error(f'send_vip_expiry_reminder failed for {user.user_id}: {e}')
