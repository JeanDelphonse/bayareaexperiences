import threading
from datetime import date, timedelta
from flask import (render_template, redirect, url_for, flash,
                   request, jsonify, current_app, session, abort)
from flask_login import current_user, login_required
from app.blueprints.booking import booking_bp
from app.extensions import db, mail
from app.models import Experience, Timeslot, Booking, CartItem, BookingPreferences
from app.utils import generate_pk, send_email


@booking_bp.route('/book/<experience_id>', methods=['GET', 'POST'])
@login_required
def book(experience_id):
    exp = Experience.query.filter_by(experience_id=experience_id, is_active=True).first_or_404()
    try:
        from app.tracking.events import track_event, track_funnel_step
        track_event('booking_started', category='ecommerce',
                    target_id=experience_id, target_type='experience')
        track_funnel_step('booking_start', experience_id=experience_id)
    except Exception:
        pass
    min_date = date.today() + timedelta(days=exp.advance_booking_days)
    return render_template('booking/book.html', experience=exp,
                           min_date=min_date.isoformat())


@booking_bp.route('/book/timeslot', methods=['POST'])
def get_timeslots():
    """Return available timeslots as JSON for the Fetch API."""
    data          = request.get_json(force=True)
    experience_id = data.get('experience_id')
    slot_date_str = data.get('date')
    guest_count   = int(data.get('guest_count', 1))

    try:
        slot_date = date.fromisoformat(slot_date_str)
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid date'}), 400

    slots = (Timeslot.query
             .filter_by(experience_id=experience_id, slot_date=slot_date, is_available=True)
             .filter(Timeslot.booked_count + guest_count <= Timeslot.capacity)
             .all())

    return jsonify([{
        'timeslot_id': s.timeslot_id,
        'start_time':  s.start_time.strftime('%H:%M'),
        'end_time':    s.end_time.strftime('%H:%M'),
        'remaining':   s.remaining_capacity,
    } for s in slots])


@booking_bp.route('/booking/<experience_id>/preferences', methods=['GET'])
def booking_preferences(experience_id):
    """Step 3: Persona & preference selection."""
    from app.preferences.engine import PERSONAS
    experience = Experience.query.filter_by(
        experience_id=experience_id, is_active=True).first_or_404()

    timeslot_id = request.args.get('timeslot_id') or session.get('pref_timeslot_id', '')
    pickup_city = request.args.get('pickup_city') or session.get('pref_pickup_city', '')
    tour_date   = request.args.get('tour_date')   or session.get('pref_tour_date', '')

    if not timeslot_id:
        return redirect(url_for('booking.book', experience_id=experience_id))

    timeslot = Timeslot.query.get_or_404(timeslot_id)

    # Store params in session for POST
    session['pref_experience_id'] = experience_id
    session['pref_timeslot_id']   = timeslot_id
    session['pref_pickup_city']   = pickup_city
    session['pref_tour_date']     = tour_date
    session.modified = True

    skip_url = url_for('booking.booking_preferences_skip', experience_id=experience_id)

    # Pre-fill from saved profile for logged-in users
    prefilled_personas = []
    prefilled_notes    = ''

    if current_user.is_authenticated:
        from app.models import UserPreferenceProfile
        profile = UserPreferenceProfile.query.filter_by(
            user_id=current_user.user_id).first()
        if profile:
            if profile.personas:
                prefilled_personas = [p.strip() for p in
                                      profile.personas.split(',') if p.strip()]
            prefilled_notes = profile.preference_notes or ''

    return render_template('booking/preferences.html',
                           experience=experience,
                           timeslot=timeslot,
                           personas=PERSONAS,
                           pickup_city=pickup_city,
                           skip_url=skip_url,
                           prefilled_personas=prefilled_personas,
                           prefilled_notes=prefilled_notes)


@booking_bp.route('/booking/<experience_id>/preferences', methods=['POST'])
def booking_preferences_post(experience_id):
    """Save preferences to session; proceed to cart."""
    personas_raw     = request.form.get('personas', '')
    tags_raw         = request.form.get('interest_tags', '')
    notes            = request.form.get('preference_notes', '')[:500].strip()
    save_as_defaults = request.form.get('save_as_defaults') == 'on'

    personas      = [p.strip() for p in personas_raw.split(',') if p.strip()][:3]
    interest_tags = [t.strip() for t in tags_raw.split(',')     if t.strip()]

    from app.preferences.engine import PERSONAS as _PERSONAS
    labels = ', '.join([
        next((p['label'] for p in _PERSONAS if p['id'] == pid), pid)
        for pid in personas
    ])

    session['booking_preferences'] = {
        'personas':         personas,
        'persona_labels':   labels,
        'interest_tags':    interest_tags,
        'notes':            notes,
        'save_as_defaults': save_as_defaults,
    }
    session.modified = True

    # Now add the pending cart item to cart
    experience_id_sess = session.pop('pref_experience_id', experience_id)
    timeslot_id        = session.pop('pref_timeslot_id',   '')
    pickup_city        = session.pop('pref_pickup_city',   '')
    session.pop('pref_tour_date', None)

    pending = session.pop('pending_cart_item', None)
    if pending and timeslot_id:
        _do_cart_add(
            experience_id=pending.get('experience_id', experience_id_sess),
            timeslot_id=pending.get('timeslot_id', timeslot_id),
            guest_count=pending.get('guest_count', 1),
            pickup_city=pending.get('pickup_city', pickup_city),
            pickup_address=pending.get('pickup_address', ''),
        )
        session.modified = True

    flash('Your preferences have been saved.', 'success')
    return redirect(url_for('cart.view'))


@booking_bp.route('/booking/<experience_id>/preferences/skip', methods=['GET'])
def booking_preferences_skip(experience_id):
    """Skip the preference step — add pending cart item without preferences."""
    # Clean up pref session keys
    session.pop('pref_experience_id', None)
    timeslot_id   = session.pop('pref_timeslot_id',   '')
    pickup_city   = session.pop('pref_pickup_city',   '')
    session.pop('pref_tour_date', None)
    # Mark as skipped (no personas stored — was_skipped=True will be set at confirm_booking)
    session.pop('booking_preferences', None)

    pending = session.pop('pending_cart_item', None)
    if pending and timeslot_id:
        _do_cart_add(
            experience_id=pending.get('experience_id', experience_id),
            timeslot_id=pending.get('timeslot_id', timeslot_id),
            guest_count=pending.get('guest_count', 1),
            pickup_city=pending.get('pickup_city', pickup_city),
            pickup_address=pending.get('pickup_address', ''),
        )
        session.modified = True

    return redirect(url_for('cart.view'))


@booking_bp.route('/booking/recommendations', methods=['POST'])
def booking_recommendations():
    """AJAX: generate AI recommendations for selected personas."""
    data          = request.get_json(silent=True) or {}
    experience_id = data.get('experience_id', '')
    tour_date     = data.get('tour_date', '')
    pickup_city   = data.get('pickup_city', '')
    personas      = data.get('personas', [])[:3]
    interest_tags = data.get('interest_tags', [])

    experience = Experience.query.filter_by(
        experience_id=experience_id, is_active=True).first()
    if not experience:
        return jsonify({'error': 'Experience not found'}), 404

    from app.preferences.recommendations import generate_recommendations
    result = generate_recommendations(
        experience    = experience,
        pickup_city   = pickup_city,
        tour_date     = tour_date,
        personas      = personas,
        interest_tags = interest_tags,
    )
    return jsonify(result)


def _do_cart_add(experience_id, timeslot_id, guest_count, pickup_city, pickup_address):
    """Shared helper: add an item to the cart (DB or session)."""
    exp  = Experience.query.filter_by(experience_id=experience_id, is_active=True).first()
    slot = Timeslot.query.filter_by(timeslot_id=timeslot_id).first()
    if not exp or not slot:
        return
    if current_user.is_authenticated:
        if CartItem.query.filter_by(user_id=current_user.user_id).count() >= 1:
            return
    else:
        from flask import session as _session
        if len(_session.get('cart', [])) >= 1:
            return
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
        from flask import session as _session
        cart = _session.get('cart', [])
        cart.append({
            'cart_item_id':   generate_pk(),
            'experience_id':  experience_id,
            'timeslot_id':    timeslot_id,
            'guest_count':    guest_count,
            'pickup_city':    pickup_city,
            'pickup_address': pickup_address,
        })
        _session['cart'] = cart
        _session.modified = True


@booking_bp.route('/book/confirm', methods=['POST'])
@login_required
def confirm_booking():
    """Process booking after payment (called post-checkout or for offline/deposit modes)."""
    experience_id     = request.form.get('experience_id')
    timeslot_id       = request.form.get('timeslot_id')
    guest_count       = int(request.form.get('guest_count', 1))
    pickup_city       = request.form.get('pickup_city')
    pickup_address    = request.form.get('pickup_address', '')
    first_name        = request.form.get('first_name', '').strip()
    last_name         = request.form.get('last_name', '').strip()
    guest_email       = request.form.get('email', '').strip().lower()
    guest_phone       = request.form.get('phone', '').strip()
    special           = request.form.get('special_requests', '').strip()
    payment_intent_id = request.form.get('payment_intent_id', '')
    # Loyalty fields passed from checkout form hidden inputs
    discount_code_id  = request.form.get('discount_code_id', '').strip() or None
    discount_amount   = float(request.form.get('discount_amount', 0) or 0)
    credit_applied    = float(request.form.get('credit_applied', 0) or 0)
    original_amount   = float(request.form.get('original_amount', 0) or 0)

    if not all([first_name, last_name, guest_email, guest_phone]):
        flash('First name, last name, email, and phone are required.', 'danger')
        return redirect(url_for('checkout.checkout'))

    exp = Experience.query.filter_by(experience_id=experience_id, is_active=True).first_or_404()

    # Transactional lock to prevent double-booking
    slot = (Timeslot.query
            .filter_by(timeslot_id=timeslot_id, experience_id=experience_id)
            .with_for_update()
            .first_or_404())

    if slot.booked_count + guest_count > slot.capacity:
        flash('Sorry, that timeslot just became fully booked. Please choose another.', 'danger')
        return redirect(url_for('booking.book', experience_id=experience_id))

    amount_total = float(exp.effective_price)
    amount_paid  = amount_total if payment_intent_id else 0.0
    amount_due   = 0.0 if payment_intent_id else amount_total
    payment_status = 'paid' if payment_intent_id else ('offline' if exp.payment_mode == 'offline' else 'pending')

    booking = Booking(
        booking_id=generate_pk(),
        user_id=current_user.user_id if current_user.is_authenticated else None,
        experience_id=experience_id,
        timeslot_id=timeslot_id,
        staff_id=exp.staff_id,
        guest_first_name=first_name,
        guest_last_name=last_name,
        guest_email=guest_email,
        guest_phone=guest_phone,
        guest_count=guest_count,
        pickup_city=pickup_city,
        pickup_address=pickup_address,
        special_requests=special,
        payment_mode=exp.payment_mode,
        amount_total=amount_total,
        amount_paid=amount_paid,
        amount_due=amount_due,
        payment_status=payment_status,
        booking_status='confirmed',
        stripe_payment_intent_id=payment_intent_id,
    )
    db.session.add(booking)
    slot.booked_count += guest_count
    if slot.booked_count >= slot.capacity:
        slot.is_available = False

    # Save booking preferences from session
    try:
        from app.preferences.engine import PERSONAS as _PERSONAS
        from app.blueprints.account.routes import _upsert_preference_profile
        prefs_data = session.pop('booking_preferences', None)
        if prefs_data is not None:
            personas_list    = prefs_data.get('personas', [])
            interest_tags_list = prefs_data.get('interest_tags', [])
            notes_val        = prefs_data.get('notes') or None
            save_as_defaults = prefs_data.get('save_as_defaults', False)
            labels = prefs_data.get('persona_labels') or ', '.join([
                next((p['label'] for p in _PERSONAS if p['id'] == pid), pid)
                for pid in personas_list
            ])
            bp_obj = BookingPreferences(
                preference_id    = generate_pk(),
                booking_id       = booking.booking_id,
                personas         = ','.join(personas_list) or None,
                persona_labels   = labels or None,
                interest_tags    = ','.join(interest_tags_list) or None,
                preference_notes = notes_val,
                was_skipped      = not bool(personas_list),
                preference_source = 'booking_step',
            )
            db.session.add(bp_obj)
            # Optionally save as user's default profile
            if save_as_defaults and booking.user_id:
                _upsert_preference_profile(
                    user_id       = booking.user_id,
                    personas      = ','.join(personas_list),
                    interest_tags = ','.join(interest_tags_list),
                    notes         = prefs_data.get('notes', ''),
                    source        = 'booking_flow',
                )
        else:
            # No preferences in session → skipped
            bp_obj = BookingPreferences(
                preference_id     = generate_pk(),
                booking_id        = booking.booking_id,
                was_skipped       = True,
                preference_source = 'booking_step',
            )
            db.session.add(bp_obj)
    except Exception:
        pass

    # Clear cart after booking
    if current_user.is_authenticated:
        CartItem.query.filter_by(user_id=current_user.user_id).delete()
    else:
        session.pop('cart', None)

    db.session.commit()

    # Loyalty accounting (discount + referral credit)
    try:
        from app.loyalty.checkout import finalize_loyalty_accounting
        from app.loyalty.referral import get_referral_discount
        referral_info = get_referral_discount()
        friend_code   = None
        if referral_info and discount_code_id:
            from app.models import DiscountCode
            friend_code = DiscountCode.query.get(discount_code_id)
        finalize_loyalty_accounting(
            booking          = booking,
            discount_code_id = discount_code_id,
            discount_amount  = discount_amount,
            credit_applied   = credit_applied,
            original_amount  = original_amount or float(exp.price),
            final_amount     = float(exp.price) - discount_amount - credit_applied,
            referral_info    = referral_info,
            friend_code      = friend_code,
        )
        # Clear referral session after use
        if referral_info:
            session.pop('referral_code', None)
            session.pop('referral_referrer', None)
            session.pop('referral_expires', None)
            session.pop('referral_discount_pct', None)
            session.modified = True
    except Exception:
        pass

    # Queue itinerary generation asynchronously
    try:
        from app.itinerary.tasks import queue_itinerary_generation
        queue_itinerary_generation(booking.booking_id, trigger='booking_confirmed')
    except Exception:
        pass

    try:
        from app.tracking.events import track_event, track_funnel_step
        track_event('booking_completed', category='ecommerce',
                    target_id=booking.booking_id, target_type='booking')
        track_funnel_step('booking_complete', experience_id=experience_id)
    except Exception:
        pass

    # Render email templates now (request context required), then send async
    try:
        customer_html = render_template('booking/email_confirm.html', booking=booking, experience=exp)
        admin_html    = render_template('booking/email_admin_notify.html', booking=booking, experience=exp)
        _app          = current_app._get_current_object()
        _bid          = booking.booking_id
        _exp_name     = exp.name
        _guest_email  = guest_email
        _admin_email  = current_app.config['ADMIN_EMAIL']
        _fn, _ln      = first_name, last_name

        def _send_emails():
            with _app.app_context():
                try:
                    send_email(mail,
                               subject=f'Booking Confirmed — {_exp_name} (Ref: {_bid})',
                               recipients=[_guest_email], body_html=customer_html)
                    send_email(mail,
                               subject=f'New Booking: {_exp_name} — {_fn} {_ln}',
                               recipients=[_admin_email], body_html=admin_html)
                except Exception as e:
                    _app.logger.error(f'Email send failed for booking {_bid}: {e}')

        threading.Thread(target=_send_emails, daemon=True).start()
    except Exception as e:
        current_app.logger.error(f'Email setup failed for booking {booking.booking_id}: {e}')

    return redirect(url_for('booking.booking_confirm', booking_id=booking.booking_id))


@booking_bp.route('/booking/confirm/<booking_id>')
def booking_confirm(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    from flask import current_app
    from app.weather.client import fetch_forecast_for_city, fetch_forecast_for_date
    from app.weather.cities import CITY_BY_NAME, DEFAULT_CITY
    forecast = tour_day_weather = weather_tip = None
    pickup_city_display = ''
    if current_app.config.get('WEATHER_ENABLED', True):
        pickup_city_name = (booking.pickup_city or '').replace(', CA', '').strip()
        city = CITY_BY_NAME.get(pickup_city_name, DEFAULT_CITY)
        pickup_city_display = city['display']
        tour_date_str = str(booking.timeslot.slot_date)
        forecast = fetch_forecast_for_city(city, days=7)
        tour_day_weather = fetch_forecast_for_date(city['lat'], city['lng'], tour_date_str)
        weather_tip = _weather_tip(tour_day_weather)

    return render_template('booking/confirm.html', booking=booking,
                           forecast=forecast, tour_date=str(booking.timeslot.slot_date),
                           tour_day_weather=tour_day_weather, weather_tip=weather_tip,
                           pickup_city_display=pickup_city_display)


def _weather_tip(day: dict) -> str:
    if not day:
        return ''
    rain = day.get('rain_pct', 0)
    high = day.get('high_f', 70)
    cond = day.get('condition', '')
    if rain >= 50:
        return 'Rain expected on your tour day — bring a light rain jacket.'
    if rain >= 20:
        return 'Chance of showers — a layer and a compact umbrella are a good idea.'
    if 'fog' in cond.lower():
        return 'Morning fog is common in the Bay Area — it usually clears by midday.'
    if high >= 80:
        return 'Warm day ahead — sunscreen, sunglasses, and a water bottle recommended.'
    if high <= 58:
        return 'Cool day expected — a warm layer will keep you comfortable on the coast.'
    return 'Looks like a great day for your tour — light layers recommended.'


@booking_bp.route('/booking/ics/<booking_id>')
def booking_ics(booking_id):
    """Generate and download an ICS calendar file for the booking."""
    from datetime import datetime as dt
    from ics import Calendar, Event

    booking = Booking.query.get_or_404(booking_id)
    slot    = booking.timeslot
    exp     = booking.experience

    c = Calendar()
    e = Event()
    e.name    = exp.name
    e.begin   = dt.combine(slot.slot_date, slot.start_time).isoformat()
    e.end     = dt.combine(slot.slot_date, slot.end_time).isoformat()
    e.description = (
        f'Booking Reference: {booking.booking_id}\n'
        f'Guests: {booking.guest_count}\n'
        f'Pickup: {booking.pickup_city}\n'
        f'{booking.pickup_address or ""}'
    )
    e.location = booking.pickup_city
    c.events.add(e)

    from flask import Response
    return Response(
        str(c),
        mimetype='text/calendar',
        headers={'Content-Disposition': f'attachment; filename=booking_{booking_id}.ics'},
    )
