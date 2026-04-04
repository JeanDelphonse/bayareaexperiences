"""Monthly performance evaluation cron job.

Run on the 1st of each month at 00:30 UTC:
  30 0 1 * *  /path/to/venv/python -c \
    "from app import create_app; app=create_app(); app.app_context().push(); \
     from app.marketplace.performance import evaluate_provider_performance; \
     evaluate_provider_performance()"
"""
from datetime import date, timedelta
from app.extensions import db


def evaluate_provider_performance():
    """
    Evaluate each active Free tier provider's confirmed booking count
    for the previous calendar month and update commission rates accordingly.
    """
    from app.models import Provider, Booking, Experience
    from app.marketplace.email import (
        send_performance_rate_earned,
        send_performance_rate_locked,
        send_performance_rate_lost,
    )

    today           = date.today()
    first_this      = today.replace(day=1)
    last_month_end  = first_this - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    THRESHOLD = 10

    free_providers = Provider.query.filter_by(tier='free', is_active=True).all()

    for provider in free_providers:
        count = (
            Booking.query
            .join(Experience, Booking.experience_id == Experience.experience_id)
            .filter(
                Experience.provider_id    == provider.provider_id,
                Booking.booking_status    == 'confirmed',
                Booking.created_at        >= last_month_start,
                Booking.created_at        <= last_month_end,
            ).count()
        )

        if count >= THRESHOLD:
            prev_consec = provider.performance_months_consecutive or 0
            # Reset grace-month marker if they're back above threshold
            if prev_consec < 0:
                prev_consec = 0
            provider.performance_months_consecutive = prev_consec + 1
            provider.performance_commission_rate    = 12.0
            provider.performance_last_evaluated     = today

            if provider.performance_months_consecutive == 1:
                send_performance_rate_earned(provider, count)
            elif (provider.performance_months_consecutive >= 3
                  and not provider.performance_locked_in):
                provider.performance_locked_in = True
                send_performance_rate_locked(provider)

        else:
            # Below threshold
            if provider.performance_commission_rate is not None:
                if provider.performance_locked_in:
                    if provider.performance_months_consecutive == -1:
                        # Second consecutive miss — revert
                        provider.performance_commission_rate    = None
                        provider.performance_locked_in          = False
                        provider.performance_months_consecutive = 0
                        send_performance_rate_lost(provider)
                    else:
                        # First miss — grace month
                        provider.performance_months_consecutive = -1
                else:
                    # Not locked in — revert immediately
                    provider.performance_commission_rate    = None
                    provider.performance_months_consecutive = 0
            else:
                # No rate active, just reset consecutive counter
                provider.performance_months_consecutive = 0

            provider.performance_last_evaluated = today

    db.session.commit()
