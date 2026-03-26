from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.blueprints.account import account_bp
from app.extensions import db, bcrypt
from app.models import Booking


@account_bp.route('/dashboard')
@login_required
def dashboard():
    return redirect(url_for('account.bookings'))


@account_bp.route('/dashboard/bookings')
@login_required
def bookings():
    user_bookings = (Booking.query
                     .filter_by(user_id=current_user.user_id)
                     .order_by(Booking.created_at.desc())
                     .all())
    return render_template('account/bookings.html', bookings=user_bookings)


@account_bp.route('/dashboard/bookings/<booking_id>')
@login_required
def booking_detail(booking_id):
    import json
    from app.itinerary.storage import get_active_itinerary
    booking = Booking.query.filter_by(
        booking_id=booking_id,
        user_id=current_user.user_id,
    ).first_or_404()
    itinerary_record = get_active_itinerary(booking_id)
    itinerary = None
    if itinerary_record:
        try:
            itinerary = json.loads(itinerary_record.itinerary_json)
        except (ValueError, TypeError):
            itinerary = None
    return render_template(
        'account/booking_detail.html',
        booking=booking,
        itinerary=itinerary,
        itinerary_version=itinerary_record.version if itinerary_record else None,
        itinerary_generated_at=itinerary_record.generated_at if itinerary_record else None,
        is_fallback=itinerary_record.is_fallback if itinerary_record else False,
    )


@account_bp.route('/dashboard/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.first_name = request.form.get('first_name', '').strip()
        current_user.last_name  = request.form.get('last_name', '').strip()
        current_user.phone      = request.form.get('phone', '').strip()
        current_user.address    = request.form.get('address', '').strip()
        current_user.city       = request.form.get('city', '').strip()
        current_user.state      = request.form.get('state', '').strip()
        current_user.postal_zip = request.form.get('postal_zip', '').strip()
        current_user.notes      = request.form.get('notes', '').strip()
        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('account.profile'))
    return render_template('account/profile.html')


@account_bp.route('/dashboard/password', methods=['POST'])
@login_required
def change_password():
    current_pw = request.form.get('current_password', '')
    new_pw     = request.form.get('new_password', '')
    confirm    = request.form.get('confirm_password', '')
    if not bcrypt.check_password_hash(current_user.password_hash, current_pw):
        flash('Current password is incorrect.', 'danger')
    elif new_pw != confirm or len(new_pw) < 8:
        flash('New passwords must match and be at least 8 characters.', 'danger')
    else:
        current_user.password_hash = bcrypt.generate_password_hash(new_pw, rounds=12).decode('utf-8')
        db.session.commit()
        flash('Password changed successfully.', 'success')
    return redirect(url_for('account.profile'))
