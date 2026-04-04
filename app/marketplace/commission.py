"""Commission rate helpers and referral credit logic."""
from app.extensions import db


def effective_commission_rate(provider) -> float:
    """
    Return the commission percentage that applies to a booking
    for the given provider right now.
    Priority: Pro tier → performance rate → standard Free rate.
    """
    if provider.tier == 'pro':
        return float(provider.processing_fee_rate)
    if provider.performance_commission_rate is not None:
        return float(provider.performance_commission_rate)
    return float(provider.commission_rate)


def calculate_commission(booking_amount: float, provider) -> dict:
    """Returns a breakdown of commission and provider payout for a booking."""
    rate     = effective_commission_rate(provider)
    comm_amt = round(booking_amount * rate / 100, 2)
    prov_amt = round(booking_amount - comm_amt, 2)
    return {
        'booking_amount':    booking_amount,
        'commission_rate':   rate,
        'commission_amount': comm_amt,
        'provider_payout':   prov_amt,
    }


def apply_referral_credit(provider, commission_due: float) -> dict:
    """
    Apply any available referral credit against a commission charge.
    Returns updated amounts and credit used.
    """
    balance = float(provider.referral_credit_balance or 0)
    applied = min(balance, commission_due)
    net_due = round(commission_due - applied, 2)

    if applied > 0:
        provider.referral_credit_balance = round(balance - applied, 2)
        db.session.commit()

    return {
        'commission_due':     commission_due,
        'credit_applied':     round(applied, 2),
        'net_commission_due': net_due,
    }


def track_provider_referral_booking(provider):
    """
    Increment the booking count on any pending provider referral for this provider.
    Trigger credit when 5-booking threshold is reached.
    """
    from app.models import ProviderReferralCode
    ref = ProviderReferralCode.query.filter_by(
        referred_provider_id=provider.provider_id,
        status='pending',
    ).first()
    if not ref:
        return
    ref.bookings_completed += 1
    if ref.bookings_completed >= 5:
        process_referral_milestone(provider)
    else:
        db.session.commit()


def process_referral_milestone(referred_provider):
    """
    Called when a referred provider confirms their 5th booking.
    Credits $100 to the referrer's balance.
    """
    from app.models import ProviderReferralCode
    from app.marketplace.email import send_provider_referral_credit_notification
    from datetime import datetime, timezone

    ref = ProviderReferralCode.query.filter_by(
        referred_provider_id=referred_provider.provider_id,
        status='pending',
    ).first()
    if not ref:
        return

    referrer = ref.referrer_provider
    credit   = float(ref.credit_amount)

    referrer.referral_credit_balance = round(
        float(referrer.referral_credit_balance or 0) + credit, 2)
    ref.status      = 'credited'
    ref.credited_at = datetime.now(timezone.utc)
    db.session.commit()

    send_provider_referral_credit_notification(referrer, referred_provider, credit)
