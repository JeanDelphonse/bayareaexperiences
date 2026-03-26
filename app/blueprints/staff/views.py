"""
app/blueprints/staff/views.py — Staff portal routes.

Routes:
  GET  /my-bookings                — Staff portal home (upcoming + past bookings)
  GET  /my-bookings/<booking_id>   — Individual booking briefing in portal
  GET  /staff/setup/<token>        — Portal invite setup page
  POST /staff/setup/<token>        — Complete portal account setup
"""
from datetime import date, datetime, timezone

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.blueprints.staff import staff_bp
from app.extensions import db, bcrypt
from app.utils import generate_pk


@staff_bp.route('/my-bookings')
@login_required
def my_bookings():
    from app.models import StaffMember, ProviderStaffMember, Booking, Timeslot

    bae_staff  = StaffMember.query.filter_by(user_id=current_user.user_id).first()
    prov_staff = ProviderStaffMember.query.filter_by(user_id=current_user.user_id).first()

    if not bae_staff and not prov_staff:
        return render_template('staff/no_access.html')

    today = date.today()

    if bae_staff:
        base_q = (Booking.query
                  .join(Timeslot)
                  .filter(Booking.staff_id == bae_staff.staff_id,
                          Booking.booking_status == 'confirmed'))
    else:
        base_q = (Booking.query
                  .join(Timeslot)
                  .filter(Booking.provider_staff_id == prov_staff.provider_staff_id,
                          Booking.booking_status == 'confirmed'))

    upcoming = base_q.filter(Timeslot.slot_date >= today).order_by(Timeslot.slot_date.asc()).all()
    past     = base_q.filter(Timeslot.slot_date <  today).order_by(Timeslot.slot_date.desc()).limit(20).all()

    return render_template(
        'staff/my_bookings.html',
        staff_member=bae_staff or prov_staff,
        upcoming=upcoming,
        past=past,
    )


@staff_bp.route('/my-bookings/<booking_id>')
@login_required
def my_booking_detail(booking_id):
    from app.models import StaffMember, ProviderStaffMember, Booking

    bae_staff  = StaffMember.query.filter_by(user_id=current_user.user_id).first()
    prov_staff = ProviderStaffMember.query.filter_by(user_id=current_user.user_id).first()

    if not bae_staff and not prov_staff:
        abort(403)

    booking = Booking.query.get_or_404(booking_id)

    # Verify this booking is assigned to this staff member
    if bae_staff and booking.staff_id != bae_staff.staff_id:
        abort(403)
    if prov_staff and booking.provider_staff_id != prov_staff.provider_staff_id:
        abort(403)

    return render_template(
        'staff/my_booking_detail.html',
        booking=booking,
        staff_member=bae_staff or prov_staff,
    )


@staff_bp.route('/staff/setup/<token>', methods=['GET', 'POST'])
def portal_setup(token):
    from app.models import StaffMember, ProviderStaffMember, User

    # Find staff member by token — check both tables
    bae_staff  = StaffMember.query.filter_by(staff_portal_token=token).first()
    prov_staff = ProviderStaffMember.query.filter_by(staff_portal_token=token).first()
    staff = bae_staff or prov_staff

    if not staff:
        return render_template('staff/portal_setup.html', error='invalid')

    now = datetime.now(timezone.utc)
    expires = staff.staff_portal_token_expires
    if expires:
        # Make timezone-aware if naive (SQLite stores naive datetimes)
        if expires.tzinfo is None:
            from datetime import timezone as tz
            expires = expires.replace(tzinfo=tz.utc)
        if expires < now:
            return render_template('staff/portal_setup.html', error='expired')

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm_password', '')

        if len(password) < 8 or password != confirm:
            flash('Passwords must match and be at least 8 characters.', 'danger')
            return render_template('staff/portal_setup.html', staff=staff)

        email = staff.email
        user  = User.query.filter_by(email=email).first()

        if not user:
            # Determine first/last name
            if hasattr(staff, 'first_name'):
                first = staff.first_name
                last  = staff.last_name
            else:
                parts = staff.full_name.split(' ', 1)
                first = parts[0]
                last  = parts[1] if len(parts) > 1 else ''

            user = User(
                user_id=generate_pk(),
                first_name=first,
                last_name=last,
                email=email,
                password_hash=bcrypt.generate_password_hash(password, rounds=12).decode('utf-8'),
            )
            db.session.add(user)
            db.session.flush()
        else:
            # Update password for existing user
            user.password_hash = bcrypt.generate_password_hash(password, rounds=12).decode('utf-8')

        # Link the staff record
        staff.user_id = user.user_id
        staff.staff_portal_token = None
        staff.staff_portal_token_expires = None
        if hasattr(staff, 'can_login'):
            staff.can_login = True

        db.session.commit()

        from flask_login import login_user
        login_user(user)
        flash(f'Welcome, {user.first_name}! Your staff portal is ready.', 'success')
        return redirect(url_for('staff_portal.my_bookings'))

    return render_template('staff/portal_setup.html', staff=staff)
