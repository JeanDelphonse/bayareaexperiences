"""Marketplace notification emails — performance rate + referral credit."""
from flask import current_app, render_template
from app.utils import send_email


def send_performance_rate_earned(provider, booking_count: int):
    """Email sent the first month a Free provider hits 10+ bookings."""
    try:
        from app.extensions import mail as _mail
        avg_booking = 550
        savings = round(booking_count * avg_booking * (0.20 - 0.12), 2)
        body_html = render_template(
            'providers/email/performance_earned.html',
            provider=provider,
            booking_count=booking_count,
            savings=savings,
        )
        send_email(
            _mail,
            subject=f'Your commission rate just dropped to 12%, {provider.business_name}',
            recipients=[provider.user.email],
            body_html=body_html,
        )
    except Exception:
        pass


def send_performance_rate_locked(provider):
    """Email sent after 3 consecutive months at threshold — rate locked permanently."""
    try:
        from app.extensions import mail as _mail
        body_html = render_template(
            'providers/email/performance_locked.html',
            provider=provider,
        )
        send_email(
            _mail,
            subject=f'\U0001f512 Your 12% rate is now permanent, {provider.business_name}',
            recipients=[provider.user.email],
            body_html=body_html,
        )
    except Exception:
        pass


def send_performance_rate_lost(provider):
    """Email sent when a locked-in provider misses threshold 2 months in a row."""
    try:
        from app.extensions import mail as _mail
        body_html = render_template(
            'providers/email/performance_lost.html',
            provider=provider,
        )
        send_email(
            _mail,
            subject=f'Your commission rate has returned to 20%, {provider.business_name}',
            recipients=[provider.user.email],
            body_html=body_html,
        )
    except Exception:
        pass


def send_provider_referral_credit_notification(referrer, referred_provider, credit: float):
    """Email sent to the referring provider when their referral earns credit."""
    try:
        from app.extensions import mail as _mail
        body_html = render_template(
            'providers/email/provider_referral_credit.html',
            referrer=referrer,
            referred_provider=referred_provider,
            credit=credit,
            new_balance=float(referrer.referral_credit_balance),
        )
        send_email(
            _mail,
            subject=(
                f'$100 credit added \u2014 {referred_provider.business_name} '
                f'completed their 5th booking'
            ),
            recipients=[referrer.user.email],
            body_html=body_html,
        )
    except Exception:
        pass
