from datetime import date, timedelta
from flask import (render_template, redirect, url_for, flash,
                   request, jsonify, current_app, session, abort)
from flask_login import current_user
from app.blueprints.booking import booking_bp
from app.extensions import db, mail
from app.models import Experience, Timeslot, Booking
from app.utils import generate_pk, send_email


@booking_bp.route('/book/<experience_id>', methods=['GET', 'POST'])
def book(experience_id):
    exp = Experience.query.filter_by(experience_id=experience_id, is_active=True).first_or_404()
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


@booking_bp.route('/book/confirm', methods=['POST'])
def confirm_booking():
    """Process booking after payment (called post-checkout or for offline/deposit modes)."""
    experience_id = request.form.get('experience_id')
    timeslot_id   = request.form.get('timeslot_id')
    guest_count   = int(request.form.get('guest_count', 1))
    pickup_city   = request.form.get('pickup_city')
    pickup_address = request.form.get('pickup_address', '')
    first_name    = request.form.get('first_name', '').strip()
    last_name     = request.form.get('last_name', '').strip()
    guest_email   = request.form.get('email', '').strip().lower()
    guest_phone   = request.form.get('phone', '').strip()
    special       = request.form.get('special_requests', '').strip()
    payment_intent_id = request.form.get('payment_intent_id', '')

    exp = Experience.query.filter_by(experience_id=experience_id, is_active=True).first_or_404()

    # Transactional lock to prevent double-booking
    slot = (Timeslot.query
            .filter_by(timeslot_id=timeslot_id, experience_id=experience_id)
            .with_for_update()
            .first_or_404())

    if slot.booked_count + guest_count > slot.capacity:
        flash('Sorry, that timeslot just became fully booked. Please choose another.', 'danger')
        return redirect(url_for('booking.book', experience_id=experience_id))

    amount_total = float(exp.price)
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
    db.session.commit()

    # Send confirmation email
    try:
        send_email(
            mail,
            subject=f'Booking Confirmed — {exp.name} (Ref: {booking.booking_id})',
            recipients=[guest_email],
            body_html=render_template('booking/email_confirm.html', booking=booking, experience=exp),
        )
        # Notify admin
        send_email(
            mail,
            subject=f'New Booking: {exp.name} — {first_name} {last_name}',
            recipients=[current_app.config['ADMIN_EMAIL']],
            body_html=render_template('booking/email_admin_notify.html', booking=booking, experience=exp),
        )
    except Exception as e:
        current_app.logger.error(f'Email send failed for booking {booking.booking_id}: {e}')

    return redirect(url_for('booking.booking_confirm', booking_id=booking.booking_id))


@booking_bp.route('/booking/confirm/<booking_id>')
def booking_confirm(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    return render_template('booking/confirm.html', booking=booking)


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
