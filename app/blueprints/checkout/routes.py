import stripe
from flask import render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import current_user
from app.blueprints.checkout import checkout_bp
from app.models import Experience, Timeslot, CartItem
from app.extensions import db


@checkout_bp.route('/checkout')
def checkout():
    # Build cart preview for order summary
    if current_user.is_authenticated:
        items = CartItem.query.filter_by(user_id=current_user.user_id).all()
        cart_data = [{
            'experience': i.experience,
            'timeslot':   i.timeslot,
            'guest_count': i.guest_count,
            'pickup_city': i.pickup_city,
            'price':      float(i.experience.price),
            'cart_item_id': i.cart_item_id,
        } for i in items]
    else:
        from flask import session
        cart = session.get('cart', [])
        cart_data = []
        for item in cart:
            exp  = Experience.query.get(item['experience_id'])
            slot = Timeslot.query.get(item['timeslot_id'])
            if exp and slot:
                cart_data.append({
                    'experience':  exp,
                    'timeslot':    slot,
                    'guest_count': item['guest_count'],
                    'pickup_city': item['pickup_city'],
                    'price':       float(exp.price),
                    'cart_item_id': item['cart_item_id'],
                })

    if not cart_data:
        flash('Your cart is empty.', 'info')
        return redirect(url_for('cart.view'))

    total = sum(i['price'] for i in cart_data)
    try:
        from app.tracking.events import track_event, track_funnel_step
        track_event('checkout_started', category='ecommerce')
        track_funnel_step('checkout_start')
    except Exception:
        pass
    stripe_key = current_app.config.get('STRIPE_PUBLISHABLE_KEY', '')
    return render_template('checkout/checkout.html',
                           cart_items=cart_data, total=total,
                           stripe_key=stripe_key)


@checkout_bp.route('/checkout/create-payment-intent', methods=['POST'])
def create_payment_intent():
    """Create a Stripe PaymentIntent, routing to provider via Connect if applicable."""
    from decimal import Decimal
    from app.blueprints.payments.split import calculate_split
    data = request.get_json(force=True)
    amount_cents = int(float(data.get('amount', 0)) * 100)
    experience_id = data.get('experience_id')
    stripe.api_key = current_app.config.get('STRIPE_SECRET_KEY', '')

    try:
        # Determine if this is a provider experience
        provider_id = None
        if experience_id:
            exp = Experience.query.get(experience_id)
            if exp:
                provider_id = exp.provider_id

        split = calculate_split(Decimal(str(data.get('amount', 0))), provider_id)

        intent_kwargs = dict(
            amount=amount_cents,
            currency='usd',
            automatic_payment_methods={'enabled': True},
            metadata={
                'experience_id':    experience_id or '',
                'provider_id':      provider_id or 'BAE',
                'platform_fee':     str(split['platform_fee']),
                'provider_amount':  str(split['provider_amount']),
                'commission_rate':  str(split['commission_rate']),
                'tier':             split['tier'],
            },
        )
        # Add Connect transfer only when provider has a connected Stripe account
        if not split['is_bae_owned'] and split.get('stripe_account_id'):
            intent_kwargs['application_fee_amount'] = int(float(split['platform_fee']) * 100)
            intent_kwargs['transfer_data'] = {'destination': split['stripe_account_id']}

        intent = stripe.PaymentIntent.create(**intent_kwargs)
        return jsonify({'clientSecret': intent.client_secret})
    except (stripe.error.StripeError, ValueError) as e:
        return jsonify({'error': str(e)}), 400
