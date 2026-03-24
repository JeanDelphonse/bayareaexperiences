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
    """Create a Stripe PaymentIntent and return the client_secret."""
    data = request.get_json(force=True)
    amount_cents = int(float(data.get('amount', 0)) * 100)
    stripe.api_key = current_app.config.get('STRIPE_SECRET_KEY', '')
    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency='usd',
            automatic_payment_methods={'enabled': True},
        )
        return jsonify({'clientSecret': intent.client_secret})
    except stripe.error.StripeError as e:
        return jsonify({'error': str(e)}), 400
