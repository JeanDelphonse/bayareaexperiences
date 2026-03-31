from flask import request, jsonify, make_response, render_template, abort, current_app
from flask_login import login_required, current_user
from app.blueprints.tracking import tracking_bp
from app.extensions import db
from app.models import (Booking, TrackingSession, TrackingLocation,
                        BookingTrackingToken, StaffMember, ProviderStaffMember)
from app.utils import generate_pk
from datetime import datetime, timezone, timedelta
import secrets


@tracking_bp.route('/tracking/beacon', methods=['POST'])
def beacon():
    """Time-on-page beacon — no auth required. Browser fire-and-forget."""
    data    = request.get_json(silent=True) or {}
    view_id = str(data.get('view_id', ''))[:9]
    seconds = data.get('time_on_page', 0)
    if view_id and isinstance(seconds, int) and 0 < seconds < 86400:
        try:
            from app.models import PageView
            PageView.query.filter_by(view_id=view_id).update(
                {'time_on_page_seconds': seconds})
            db.session.commit()
        except Exception:
            pass
    return '', 204


@tracking_bp.route('/tracking/consent', methods=['POST'])
def consent():
    """Accept or decline cookie/tracking consent."""
    data   = request.get_json(silent=True) or {}
    accept = bool(data.get('accept', False))

    resp = make_response(jsonify({'ok': True}))
    resp.set_cookie(
        'tracking_consent',
        '1' if accept else '0',
        max_age=365 * 24 * 3600,
        httponly=True,
        samesite='Lax',
    )

    try:
        from flask import session as flask_session
        from app.models import SiteSession
        session_id = flask_session.get('tracking_session_id')
        if session_id:
            site_sess = SiteSession.query.get(session_id)
            if site_sess:
                site_sess.consent_given = accept
                db.session.commit()
    except Exception:
        pass

    return resp


# ── GPS: Staff — Start tracking session ──────────────────────────────────────

@tracking_bp.route('/tracking/start/<booking_id>', methods=['POST'])
@login_required
def start_tracking(booking_id):
    bae_staff  = StaffMember.query.filter_by(user_id=current_user.user_id).first()
    prov_staff = ProviderStaffMember.query.filter_by(user_id=current_user.user_id).first()
    if not bae_staff and not prov_staff:
        return jsonify({'error': 'Not authorised'}), 403

    booking = Booking.query.get_or_404(booking_id)

    if not booking.tracking_enabled:
        return jsonify({'error': 'Tracking disabled for this booking'}), 403

    # Verify assignment
    is_assigned = (
        (bae_staff  and booking.staff_id          == bae_staff.staff_id) or
        (prov_staff and booking.provider_staff_id == prov_staff.provider_staff_id)
    )
    if not is_assigned:
        return jsonify({'error': 'Not assigned to this booking'}), 403

    # End any existing active session
    existing = TrackingSession.query.filter_by(
        booking_id=booking_id, status='active').first()
    if existing:
        existing.status   = 'ended'
        existing.ended_at = datetime.now(timezone.utc)

    # Get or create tracking token
    token_record = BookingTrackingToken.query.filter_by(booking_id=booking_id).first()
    if not token_record:
        timeslot  = booking.timeslot
        tour_end  = datetime.combine(
            timeslot.slot_date, timeslot.end_time, tzinfo=timezone.utc)
        token_record = BookingTrackingToken(
            token_id   = generate_pk(),
            booking_id = booking_id,
            token      = secrets.token_hex(32),
            expires_at = tour_end + timedelta(hours=current_app.config.get('GPS_TOKEN_TTL_HOURS', 6)),
            is_active  = False,
        )
        db.session.add(token_record)

    session = TrackingSession(
        session_id          = generate_pk(),
        booking_id          = booking_id,
        staff_user_id       = current_user.user_id,
        tracking_token      = token_record.token,
        status              = 'active',
        started_at          = datetime.now(timezone.utc),
        staff_consent_given = True,
    )
    db.session.add(session)
    token_record.is_active = True
    db.session.commit()

    return jsonify({'session_id': session.session_id, 'ok': True})


# ── GPS: Staff — End tracking session ────────────────────────────────────────

@tracking_bp.route('/tracking/end/<booking_id>', methods=['POST'])
@login_required
def end_tracking(booking_id):
    bae_staff  = StaffMember.query.filter_by(user_id=current_user.user_id).first()
    prov_staff = ProviderStaffMember.query.filter_by(user_id=current_user.user_id).first()
    if not bae_staff and not prov_staff:
        return jsonify({'error': 'Not authorised'}), 403

    session = TrackingSession.query.filter_by(
        booking_id=booking_id, status='active').first()
    if session:
        session.status   = 'ended'
        session.ended_at = datetime.now(timezone.utc)
        token_record = BookingTrackingToken.query.filter_by(
            booking_id=booking_id).first()
        if token_record:
            token_record.is_active = False
        db.session.commit()
    return jsonify({'ok': True})


# ── GPS: Customer — Live tracking page ───────────────────────────────────────

@tracking_bp.route('/track/<token>')
def customer_tracking(token):
    token_record = BookingTrackingToken.query.filter_by(token=token).first()
    if not token_record:
        abort(404)
    if token_record.expires_at < datetime.now(timezone.utc):
        return render_template('tracking/expired.html')

    booking = token_record.booking
    session = TrackingSession.query.filter_by(
        booking_id=booking.booking_id, status='active').first()

    if session:
        session.customer_views += 1
        db.session.commit()

    # Resolve pickup lat/lng if pickup_address is available — fall back to city centre
    pickup_lat = None
    pickup_lng = None

    return render_template(
        'tracking/customer_map.html',
        booking=booking,
        session=session,
        token=token,
        pickup_lat=pickup_lat,
        pickup_lng=pickup_lng,
        GOOGLE_MAPS_API_KEY=current_app.config.get('GOOGLE_MAPS_API_KEY', ''),
    )


# ── GPS: Token expired page ───────────────────────────────────────────────────

@tracking_bp.route('/tracking/expired')
def tracking_expired():
    return render_template('tracking/expired.html')
