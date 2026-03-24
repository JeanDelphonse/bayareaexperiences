"""Stripe webhook handler — /payments/webhook"""
import stripe
from datetime import datetime, timezone
from flask import request, current_app
from app.blueprints.payments import payments_bp
from app.extensions import db
from app.utils import generate_pk, send_email


@payments_bp.route('/payments/webhook', methods=['POST'])
def stripe_webhook():
    payload    = request.data
    sig_header = request.headers.get('Stripe-Signature', '')
    secret     = current_app.config.get('STRIPE_WEBHOOK_SECRET', '')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        return '', 400

    etype = event['type']

    if etype == 'checkout.session.completed':
        _handle_checkout_completed(event['data']['object'])

    elif etype == 'transfer.paid':
        _handle_transfer_paid(event['data']['object'])

    elif etype in ('customer.subscription.created', 'customer.subscription.updated'):
        _handle_subscription_updated(event['data']['object'])

    elif etype == 'customer.subscription.deleted':
        _handle_subscription_deleted(event['data']['object'])

    elif etype == 'invoice.payment_failed':
        _handle_invoice_failed(event['data']['object'])

    elif etype == 'invoice.payment_succeeded':
        _handle_invoice_succeeded(event['data']['object'])

    return '', 200


def _handle_checkout_completed(session):
    from app.models import Booking, ProviderPayout
    meta = session.get('metadata', {}) or {}
    booking_id = meta.get('booking_id')
    if not booking_id:
        return

    booking = Booking.query.get(booking_id)
    if not booking:
        return

    booking.booking_status           = 'confirmed'
    booking.stripe_payment_intent_id = session.get('payment_intent', '')
    booking.amount_paid              = booking.amount_total
    booking.amount_due               = 0
    booking.payment_status           = 'paid'
    booking.platform_fee_amount      = float(meta.get('platform_fee', 0))
    booking.provider_amount          = float(meta.get('provider_amount', 0))

    provider_id = meta.get('provider_id')
    if provider_id and provider_id != 'BAE':
        payout = ProviderPayout(
            payout_id                = generate_pk(),
            provider_id              = provider_id,
            booking_id               = booking_id,
            booking_amount           = float(meta.get('booking_amount', booking.amount_total)),
            platform_fee             = float(meta.get('platform_fee', 0)),
            provider_amount          = float(meta.get('provider_amount', 0)),
            stripe_payment_intent_id = session.get('payment_intent', ''),
            stripe_transfer_status   = 'pending',
            tier_at_time             = meta.get('tier', 'free'),
            commission_rate_applied  = float(meta.get('commission_rate', 20)),
        )
        db.session.add(payout)

    db.session.commit()


def _handle_transfer_paid(transfer):
    from app.models import ProviderPayout
    payout = ProviderPayout.query.filter_by(stripe_transfer_id=transfer['id']).first()
    if payout:
        payout.stripe_transfer_status = 'paid'
        payout.transfer_completed_at  = datetime.now(timezone.utc)
        db.session.commit()


def _handle_subscription_updated(subscription):
    from app.models import Provider
    provider = Provider.query.filter_by(subscription_id=subscription['id']).first()
    if not provider:
        # Try to match via customer_id
        provider = Provider.query.filter_by(stripe_customer_id=subscription.get('customer')).first()
    if not provider:
        return

    provider.subscription_id     = subscription['id']
    provider.subscription_status = subscription['status']
    period_end = subscription.get('current_period_end')
    if period_end:
        provider.current_period_end = datetime.fromtimestamp(period_end, tz=timezone.utc)
    if subscription['status'] == 'active':
        provider.tier               = 'pro'
        provider.commission_rate    = provider.commission_rate   # keep
        provider.experience_limit   = 9999
    db.session.commit()


def _handle_subscription_deleted(subscription):
    from app.models import Provider
    provider = Provider.query.filter_by(subscription_id=subscription['id']).first()
    if not provider:
        return
    provider.subscription_status = 'canceled'
    provider.tier                 = 'free'
    provider.commission_rate      = 20.00
    provider.experience_limit     = 5
    db.session.commit()

    # Notify provider
    try:
        from flask_mail import Message
        from app.extensions import mail
        msg = Message(
            subject='Your BAE Pro subscription has been cancelled',
            recipients=[provider.user.email],
        )
        msg.body = (
            f'Hi {provider.user.first_name},\n\n'
            'Your Pro subscription has been cancelled. Your account has been moved to the '
            'Free Tier (20% commission, 5-experience limit).\n\n'
            'You can reactivate Pro any time from your provider dashboard.\n\n'
            'Bay Area Experiences'
        )
        mail.send(msg)
    except Exception:
        pass


def _handle_invoice_failed(invoice):
    from app.models import Provider
    provider = Provider.query.filter_by(stripe_customer_id=invoice.get('customer')).first()
    if not provider:
        return
    provider.subscription_status = 'past_due'
    db.session.commit()

    try:
        from flask_mail import Message
        from app.extensions import mail
        msg = Message(
            subject='Action required: Pro subscription payment failed',
            recipients=[provider.user.email],
        )
        msg.body = (
            f'Hi {provider.user.first_name},\n\n'
            'We were unable to process your Pro subscription payment. '
            'Please update your payment method in the Stripe portal to avoid losing Pro benefits.\n\n'
            'Bay Area Experiences'
        )
        mail.send(msg)
    except Exception:
        pass


def _handle_invoice_succeeded(invoice):
    from app.models import Provider
    provider = Provider.query.filter_by(stripe_customer_id=invoice.get('customer')).first()
    if provider:
        provider.subscription_status = 'active'
        db.session.commit()
