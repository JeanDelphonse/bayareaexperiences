from flask import render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import current_user
from app.blueprints.cart import cart_bp
from app.extensions import db
from app.models import Experience, Timeslot, CartItem
from app.utils import generate_pk


def _get_session_cart():
    return session.get('cart', [])


def _save_session_cart(cart):
    session['cart'] = cart
    session.modified = True


@cart_bp.route('/cart/add', methods=['POST'])
def add():
    experience_id  = request.form.get('experience_id')
    timeslot_id    = request.form.get('timeslot_id')
    guest_count    = int(request.form.get('guest_count', 1))
    pickup_city    = request.form.get('pickup_city')
    pickup_address = request.form.get('pickup_address', '')

    exp  = Experience.query.filter_by(experience_id=experience_id, is_active=True).first_or_404()
    slot = Timeslot.query.filter_by(timeslot_id=timeslot_id).first_or_404()

    if current_user.is_authenticated:
        item = CartItem(
            cart_item_id=generate_pk(),
            user_id=current_user.user_id,
            experience_id=experience_id,
            timeslot_id=timeslot_id,
            guest_count=guest_count,
            pickup_city=pickup_city,
            pickup_address=pickup_address,
        )
        db.session.add(item)
        db.session.commit()
    else:
        cart = _get_session_cart()
        cart.append({
            'cart_item_id':  generate_pk(),
            'experience_id': experience_id,
            'timeslot_id':   timeslot_id,
            'guest_count':   guest_count,
            'pickup_city':   pickup_city,
            'pickup_address': pickup_address,
        })
        _save_session_cart(cart)

    flash(f'"{exp.name}" added to cart.', 'success')
    return redirect(url_for('cart.view'))


@cart_bp.route('/cart')
def view():
    if current_user.is_authenticated:
        items = CartItem.query.filter_by(user_id=current_user.user_id).all()
        cart_data = []
        for item in items:
            cart_data.append({
                'cart_item_id': item.cart_item_id,
                'experience':   item.experience,
                'timeslot':     item.timeslot,
                'guest_count':  item.guest_count,
                'pickup_city':  item.pickup_city,
                'pickup_address': item.pickup_address,
                'price':        float(item.experience.price),
            })
    else:
        cart = _get_session_cart()
        cart_data = []
        for item in cart:
            exp  = Experience.query.get(item['experience_id'])
            slot = Timeslot.query.get(item['timeslot_id'])
            if exp and slot:
                cart_data.append({
                    'cart_item_id': item['cart_item_id'],
                    'experience':   exp,
                    'timeslot':     slot,
                    'guest_count':  item['guest_count'],
                    'pickup_city':  item['pickup_city'],
                    'pickup_address': item.get('pickup_address', ''),
                    'price':        float(exp.price),
                })

    total = sum(i['price'] for i in cart_data)
    return render_template('cart/cart.html', cart_items=cart_data, total=total)


@cart_bp.route('/cart/remove/<item_id>', methods=['POST'])
def remove(item_id):
    if current_user.is_authenticated:
        item = CartItem.query.filter_by(
            cart_item_id=item_id, user_id=current_user.user_id
        ).first_or_404()
        db.session.delete(item)
        db.session.commit()
    else:
        cart = _get_session_cart()
        cart = [i for i in cart if i['cart_item_id'] != item_id]
        _save_session_cart(cart)
    flash('Item removed from cart.', 'info')
    return redirect(url_for('cart.view'))
