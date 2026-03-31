"""Loyalty discount detection and post-booking accounting."""
import os
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

LOYALTY_ENABLED = os.environ.get('LOYALTY_ENABLED', 'True').lower() not in ('false', '0', 'no')


def get_applicable_discount(user):
    """
    Find the best active discount for a logged-in user.
    Returns DiscountCode or None.
    """
    if not LOYALTY_ENABLED or not user or not user.is_vip:
        return None

    from app.models import VipCustomer, DiscountCode

    vip = VipCustomer.query.filter_by(
        user_id=user.user_id,
        status='active',
    ).order_by(VipCustomer.vip_earned_at.desc()).first()
    if not vip:
        return None

    code = DiscountCode.query.filter_by(
        code_id=vip.discount_code_id,
        is_active=True,
    ).filter(DiscountCode.times_used < DiscountCode.max_uses).first()
    if not code:
        return None

    if code.expires_at and code.expires_at < datetime.now(timezone.utc):
        code.is_active = False
        from app.extensions import db
        db.session.commit()
        return None

    return code


def calculate_discount_amount(subtotal: Decimal, code) -> Decimal:
    """Dollar discount from a percentage code."""
    if not code or not code.discount_percent:
        return Decimal('0.00')
    return (subtotal * Decimal(str(code.discount_percent)) / 100).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP)


def calculate_final_amounts(subtotal: Decimal, discount_code, referral_credit_balance: Decimal) -> dict:
    """Return full breakdown: subtotal, discount, credit, final."""
    discount_amt   = calculate_discount_amount(subtotal, discount_code)
    after_discount = subtotal - discount_amt
    credit_applied = min(Decimal(str(referral_credit_balance)), after_discount)
    final          = max(after_discount - credit_applied, Decimal('0.00'))
    return {
        'subtotal':        subtotal,
        'discount_amount': discount_amt,
        'credit_applied':  credit_applied,
        'final_amount':    final,
    }


def finalize_loyalty_accounting(booking, discount_code_id, discount_amount,
                                 credit_applied, original_amount, final_amount,
                                 referral_info=None, friend_code=None):
    """
    Called after booking is confirmed.
    - Marks VIP discount code used
    - Deducts referral credit from user balance
    - Creates DiscountRedemption record
    - Creates ReferralRedemption + notifies referrer if referral booking
    Never raises.
    """
    if not LOYALTY_ENABLED:
        return
    try:
        from app.models import VipCustomer, DiscountCode, DiscountRedemption, User, ReferralLink
        from app.extensions import db
        from app.utils import generate_pk
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        discount_amount  = Decimal(str(discount_amount))
        credit_applied   = Decimal(str(credit_applied))
        original_amount  = Decimal(str(original_amount))
        final_amount     = Decimal(str(final_amount))

        if discount_code_id:
            code = DiscountCode.query.get(discount_code_id)
            if code:
                code.times_used += 1
                if code.times_used >= code.max_uses:
                    code.is_active = False
                redemption = DiscountRedemption(
                    redemption_id   = generate_pk(),
                    code_id         = code.code_id,
                    booking_id      = booking.booking_id,
                    user_id         = booking.user_id,
                    original_amount = original_amount,
                    discount_amount = discount_amount,
                    final_amount    = final_amount,
                    redeemed_at     = now,
                )
                db.session.add(redemption)
                booking.discount_code_id = discount_code_id
                booking.discount_amount  = discount_amount

                if code.code_type == 'vip_loyalty' and booking.user_id:
                    vip = VipCustomer.query.filter_by(discount_code_id=code.code_id).first()
                    if vip:
                        vip.status = 'discount_used'

        if credit_applied > 0 and booking.user_id:
            user = User.query.get(booking.user_id)
            if user:
                user.total_referral_credit_balance = max(
                    Decimal(str(user.total_referral_credit_balance)) - credit_applied,
                    Decimal('0.00'),
                )
                booking.referral_credit_applied = credit_applied
                vip = VipCustomer.query.filter_by(
                    user_id=user.user_id,
                ).order_by(VipCustomer.vip_earned_at.desc()).first()
                if vip:
                    vip.referral_credit_used = Decimal(str(vip.referral_credit_used)) + credit_applied

        db.session.commit()

        # Process referral completion (friend's booking)
        if referral_info:
            try:
                from app.loyalty.referral import process_referral_completion
                process_referral_completion(booking, referral_info, friend_code)
            except Exception as e:
                import logging
                logging.getLogger('loyalty').error(f'process_referral_completion failed: {e}')

    except Exception as e:
        import logging
        logging.getLogger('loyalty').error(f'finalize_loyalty_accounting failed: {e}')
