"""VIP grant logic — called when a 5-star review is published."""
import logging
import os
from datetime import datetime, timezone, timedelta

log = logging.getLogger('loyalty')

LOYALTY_ENABLED = os.environ.get('LOYALTY_ENABLED', 'True').lower() not in ('false', '0', 'no')
VIP_EXPIRY_DAYS = int(os.environ.get('VIP_DISCOUNT_EXPIRY_DAYS', 365))


def maybe_grant_vip(review, booking) -> bool:
    """
    Called when a review is published.
    If star_rating == 5 and reviewer has a user account, grant VIP + issue discount code.
    Returns True if VIP was granted. Never raises.
    """
    if not LOYALTY_ENABLED:
        return False
    try:
        if review.star_rating != 5:
            return False
        if not review.user_id:
            return False  # Guest reviewer — handled by /loyalty/claim after registration

        from app.models import VipCustomer, User
        from app.extensions import db
        from app.utils import generate_pk
        from app.loyalty.codes import generate_vip_discount_code, generate_referral_code

        user = User.query.get(review.user_id)
        if not user:
            return False

        # Idempotency — one VIP record per qualifying review
        existing = VipCustomer.query.filter_by(qualifying_review_id=review.review_id).first()
        if existing:
            return False

        now = datetime.now(timezone.utc)

        discount_code = generate_vip_discount_code(user)
        db.session.add(discount_code)
        db.session.flush()

        referral_code_str = generate_referral_code(user)

        vip = VipCustomer(
            vip_id                  = generate_pk(),
            user_id                 = user.user_id,
            qualifying_review_id    = review.review_id,
            qualifying_booking_id   = booking.booking_id,
            status                  = 'active',
            discount_code_id        = discount_code.code_id,
            referral_code           = referral_code_str,
            vip_earned_at           = now,
            discount_expires_at     = now + timedelta(days=VIP_EXPIRY_DAYS),
        )
        db.session.add(vip)
        user.is_vip = True
        db.session.commit()

        # Send VIP welcome email (non-blocking)
        try:
            from app.loyalty.email import send_vip_welcome_email
            send_vip_welcome_email(user, vip, discount_code)
        except Exception as e:
            log.error(f'VIP welcome email failed for {user.user_id}: {e}')

        log.info(f'VIP granted: user={user.user_id} review={review.review_id}')
        return True

    except Exception as e:
        log.error(f'maybe_grant_vip failed for review {review.review_id}: {e}')
        try:
            from app.extensions import db
            db.session.rollback()
        except Exception:
            pass
        return False
