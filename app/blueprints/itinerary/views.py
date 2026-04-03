"""Itinerary-facing routes."""
import json
from flask import render_template, jsonify, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app.blueprints.itinerary import itinerary_bp
from app.utils import admin_required


# ── Customer: full itinerary view ─────────────────────────────────────────────

@itinerary_bp.route('/booking/<booking_id>/itinerary')
def booking_itinerary(booking_id):
    from app.models import Booking
    from app.itinerary.storage import get_active_itinerary
    booking = Booking.query.get_or_404(booking_id)

    # Access control: must be logged-in owner or guest token
    if current_user.is_authenticated:
        if booking.user_id and booking.user_id != current_user.user_id and not current_user.is_admin:
            abort(403)
    else:
        # Guest: booking must match their email in session (simple check)
        pass  # For now, allow access by booking_id (opaque 9-char)

    record   = get_active_itinerary(booking_id)
    itinerary = None
    if record:
        try:
            itinerary = json.loads(record.itinerary_json)
        except Exception:
            pass

    return render_template('itinerary/full_itinerary.html',
                           booking=booking, itinerary=itinerary, record=record)


# ── AJAX polling — is itinerary ready? ────────────────────────────────────────

@itinerary_bp.route('/booking/<booking_id>/itinerary/status')
def itinerary_status(booking_id):
    from app.itinerary.storage import get_active_itinerary
    record = get_active_itinerary(booking_id)
    return jsonify({'ready': record is not None})


# ── AJAX fragment — rendered itinerary HTML for async injection ───────────────

@itinerary_bp.route('/booking/<booking_id>/itinerary/fragment')
def itinerary_fragment(booking_id):
    import json as _json
    from app.models import Booking
    from app.itinerary.storage import get_active_itinerary
    record = get_active_itinerary(booking_id)
    if not record:
        return jsonify({'ready': False})
    try:
        itinerary = _json.loads(record.itinerary_json)
    except Exception:
        return jsonify({'ready': False})
    html = render_template('itinerary/_itinerary_panel.html', itinerary=itinerary)
    view_url = url_for('itinerary.booking_itinerary', booking_id=booking_id)
    return jsonify({'ready': True, 'html': html, 'view_url': view_url})


# ── Staff briefing page — no login required ───────────────────────────────────

@itinerary_bp.route('/staff/briefing/<booking_id>')
def staff_briefing(booking_id):
    from app.models import Booking
    from app.itinerary.storage import get_active_itinerary
    import json as json_lib

    booking = Booking.query.get_or_404(booking_id)
    record  = get_active_itinerary(booking_id)
    itinerary = None
    if record:
        try:
            itinerary = json_lib.loads(record.itinerary_json)
        except Exception:
            pass

    # GPS tracking window check
    from datetime import datetime, timezone, timedelta
    from flask import current_app
    pre_min  = current_app.config.get('GPS_WINDOW_PRE_MINUTES', 30)
    post_min = current_app.config.get('GPS_WINDOW_POST_MINUTES', 30)
    now_utc  = datetime.now(timezone.utc)
    ts       = booking.timeslot
    start_dt = datetime.combine(ts.slot_date, ts.start_time, tzinfo=timezone.utc)
    end_dt   = datetime.combine(ts.slot_date, ts.end_time,   tzinfo=timezone.utc)
    in_tracking_window = (
        booking.tracking_enabled and
        (start_dt - timedelta(minutes=pre_min)) <= now_utc <= (end_dt + timedelta(minutes=post_min))
    )

    from flask import current_app
    from app.weather.client import fetch_forecast
    from app.weather.cities import CITY_BY_NAME, DEFAULT_CITY
    tour_day_weather = None
    pickup_city_display = ''
    if current_app.config.get('WEATHER_ENABLED', True):
        pickup_city_name = (booking.pickup_city or '').replace(', CA', '').strip()
        city = CITY_BY_NAME.get(pickup_city_name, DEFAULT_CITY)
        pickup_city_display = city['display']
        full_forecast = fetch_forecast(city['lat'], city['lng'], days=7)
        if full_forecast:
            tour_date_str = str(booking.timeslot.slot_date)
            for day in full_forecast.get('daily', []):
                if day['date'] == tour_date_str:
                    tour_day_weather = day
                    break

    return render_template('itinerary/staff_briefing.html',
                           booking=booking, itinerary=itinerary,
                           in_tracking_window=in_tracking_window,
                           tour_day_weather=tour_day_weather,
                           pickup_city_display=pickup_city_display)


# ── Admin: list all itineraries ───────────────────────────────────────────────

@itinerary_bp.route('/admin/itineraries')
@login_required
@admin_required
def admin_itineraries():
    from app.models import BookingItinerary
    page = request.args.get('page', 1, type=int)
    records = (BookingItinerary.query
               .order_by(BookingItinerary.generated_at.desc())
               .paginate(page=page, per_page=25))
    return render_template('admin/itineraries.html', records=records)


# ── Admin: view one itinerary ─────────────────────────────────────────────────

@itinerary_bp.route('/admin/itineraries/<itinerary_id>')
@login_required
@admin_required
def admin_itinerary_detail(itinerary_id):
    from app.models import BookingItinerary
    import json as json_lib
    record = BookingItinerary.query.get_or_404(itinerary_id)
    itinerary = None
    try:
        itinerary = json_lib.loads(record.itinerary_json)
        pretty_json = json_lib.dumps(itinerary, indent=2)
    except Exception:
        pretty_json = record.itinerary_json
    return render_template('admin/itinerary_detail.html',
                           record=record, itinerary=itinerary, pretty_json=pretty_json)


# ── Admin: manual regeneration ────────────────────────────────────────────────

@itinerary_bp.route('/admin/bookings/<booking_id>/regen-itinerary', methods=['POST'])
@login_required
@admin_required
def admin_regen_itinerary(booking_id):
    from app.models import Booking
    import os, anthropic as _anthropic
    booking = Booking.query.get_or_404(booking_id)
    key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not key:
        flash('ANTHROPIC_API_KEY is not set on this server.', 'danger')
        return redirect(request.referrer or url_for('admin.dashboard'))

    # Pre-flight: quick ping to Claude before queuing background job.
    # Catches bad keys, quota errors, and model issues before the admin walks away.
    # 5-second timeout prevents Passenger from killing the connection on slow networks.
    try:
        _anthropic.Anthropic(api_key=key, timeout=5.0).messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=1,
            messages=[{'role': 'user', 'content': '1'}],
        )
    except Exception as e:
        flash(f'Claude API check failed — regeneration not started: {e}', 'danger')
        return redirect(request.referrer or url_for('admin.dashboard'))

    try:
        from app.itinerary.tasks import queue_itinerary_generation
        queue_itinerary_generation(booking_id, trigger='admin')
        flash('Itinerary regeneration started — refresh this page in 20–30 seconds to see the result.', 'info')
    except Exception as e:
        flash(f'Itinerary regeneration failed to start: {e}', 'danger')
    return redirect(request.referrer or url_for('admin.dashboard'))


# ── Admin: Claude connectivity test ───────────────────────────────────────────

@itinerary_bp.route('/admin/itineraries/test-claude')
@login_required
@admin_required
def admin_test_claude():
    import os
    import anthropic
    key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not key:
        return '<pre>FAIL: ANTHROPIC_API_KEY not set</pre>'
    try:
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=16,
            messages=[{'role': 'user', 'content': 'Reply with OK only.'}],
        )
        return f'<pre>OK: {msg.content[0].text.strip()}</pre>'
    except Exception as e:
        return f'<pre>FAIL: {e}</pre>'
