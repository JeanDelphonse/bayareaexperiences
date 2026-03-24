"""Payment split calculator — platform fee vs provider amount."""
from decimal import Decimal, ROUND_HALF_UP


def calculate_split(booking_amount: Decimal, provider_id) -> dict:
    """
    Calculate platform fee and provider amount.
    Returns dict with all values needed for Stripe PaymentIntent + payout record.
    """
    if not provider_id:
        # BAE-owned experience — no split
        return {
            'is_bae_owned':      True,
            'platform_fee':      booking_amount,
            'provider_amount':   Decimal('0.00'),
            'commission_rate':   Decimal('0.00'),
            'stripe_account_id': None,
            'tier':              'bae',
        }

    from app.models import Provider
    provider = Provider.query.get(provider_id)
    if not provider:
        raise ValueError(f'Provider {provider_id} not found')
    if not provider.stripe_onboarding_complete:
        raise ValueError(f'Provider {provider_id} has not completed Stripe onboarding')

    if provider.tier == 'pro':
        rate = Decimal(str(provider.processing_fee_rate))
    else:
        rate = Decimal(str(provider.commission_rate))

    platform_fee   = (booking_amount * rate / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    provider_amount = booking_amount - platform_fee

    return {
        'is_bae_owned':      False,
        'platform_fee':      platform_fee,
        'provider_amount':   provider_amount,
        'commission_rate':   rate,
        'stripe_account_id': provider.stripe_account_id,
        'tier':              provider.tier,
    }
