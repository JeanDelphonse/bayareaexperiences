"""Referral attribution — session detection and completion processing."""
import os
from datetime import datetime, timezone

LOYALTY_ENABLED    = os.environ.get('LOYALTY_ENABLED', 'True').lower() not in ('false', '0', 'no')
SESSION_TTL_DAYS   = int(os.environ.get('REFERRAL_SESSION_TTL_DAYS', 7))


def get_referral_discount() -> dict:
    """
    Check Flask session for a valid referral attribution.
    Returns dict or None.
    """
    if not LOYALTY_ENABLED:
        return None
    from flask import session as flask_session
    code         = flask_session.get('referral_code')
    expires      = flask_session.get('referral_expires', 0)
    referrer_name = flask_session.get('referral_referrer', '')

    if not code:
        return None
    if datetime.now(timezone.utc).timestamp() > expires:
        flask_session.pop('referral_code', None)
        return None

    from app.models import VipCustomer
    vip = VipCustomer.query.filter_by(referral_code=code).first()
    if not vip:
        return None

    return {
        'referral_code':    code,
        'referrer_name':    referrer_name,
        'discount_pct':     10,
        'referrer_user_id': vip.user_id,
    }


def process_referral_completion(booking, referral_info, friend_code):
    """
    Credits $25 to referrer and creates referral_redemptions record.
    Called after friend's booking is confirmed.
    """
    if not LOYALTY_ENABLED or not referral_info:
        return
    from app.models import ReferralRedemption, VipCustomer, User, ReferralLink
    from app.extensions import db
    from app.utils import generate_pk
    from decimal import Decimal
    import logging

    log = logging.getLogger('loyalty')
    now = datetime.now(timezone.utc)

    referrer = User.query.get(referral_info['referrer_user_id'])
    vip      = VipCustomer.query.filter_by(referral_code=referral_info['referral_code']).first()

    if not referrer or not vip:
        return

    credit = Decimal(str(os.environ.get('REFERRAL_CREDIT_AMOUNT', '25.00')))
    referrer.total_referral_credit_balance = (
        Decimal(str(referrer.total_referral_credit_balance)) + credit
    )
    vip.referral_credit_balance  = Decimal(str(vip.referral_credit_balance)) + credit
    vip.total_referrals_completed += 1

    redemption = ReferralRedemption(
        redemption_id          = generate_pk(),
        referrer_user_id       = referral_info['referrer_user_id'],
        referred_email         = booking.guest_email,
        referral_code          = referral_info['referral_code'],
        booking_id             = booking.booking_id,
        referrer_credit_earned = credit,
        friend_discount_code_id = friend_code.code_id if friend_code else None,
        friend_discount_amount  = Decimal(str(booking.discount_amount or 0)),
        referrer_credited_at   = now,
    )
    db.session.add(redemption)

    # Mark the referral link as converted
    link = ReferralLink.query.filter_by(
        referral_code=referral_info['referral_code'],
        converted=False,
    ).order_by(ReferralLink.clicked_at.desc()).first()
    if link:
        link.converted            = True
        link.converted_booking_id = booking.booking_id
        link.converted_at         = now

    db.session.commit()

    # Notify referrer
    try:
        from app.loyalty.email import send_referral_credit_notification
        send_referral_credit_notification(referrer, booking, vip)
    except Exception as e:
        log.error(f'Referral credit notification failed for {referrer.user_id}: {e}')
