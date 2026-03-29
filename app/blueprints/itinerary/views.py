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
    from app.itinerary.generator import generate_itinerary
    from app.itinerary.storage import save_itinerary
    booking = Booking.query.get_or_404(booking_id)
    try:
        import os, anthropic as _ac
        key = os.environ.get('ANTHROPIC_API_KEY', '')
        if not key:
            flash('ANTHROPIC_API_KEY is not set on this server.', 'danger')
            return redirect(request.referrer or url_for('admin.dashboard'))

        # Call Claude directly so any exception propagates here
        experience  = booking.experience
        client      = _ac.Anthropic(api_key=key)
        client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=16,
            messages=[{'role': 'user', 'content': 'Reply OK'}],
        )
        # Connectivity confirmed — run full generation
        itinerary = generate_itinerary(booking)
        save_itinerary(booking_id, itinerary, trigger='admin')
        flash(f'Itinerary regenerated successfully for booking {booking_id}.', 'success')
    except Exception as e:
        flash(f'Itinerary regeneration failed: {e}', 'danger')
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
