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

    return render_template('itinerary/staff_briefing.html',
                           booking=booking, itinerary=itinerary)


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
    from app.itinerary.tasks import queue_itinerary_generation
    booking = Booking.query.get_or_404(booking_id)
    queue_itinerary_generation(booking_id, trigger='admin')
    flash(f'Itinerary regeneration queued for booking {booking_id}.', 'info')
    return redirect(request.referrer or url_for('admin.dashboard'))
