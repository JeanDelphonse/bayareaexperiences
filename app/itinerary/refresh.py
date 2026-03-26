"""48-hour pre-tour itinerary refresh job."""
import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger('itinerary')


def refresh_upcoming_itineraries():
    """
    Called by cron job every 6 hours.
    Finds confirmed bookings with tours 46-50 hours away and refreshes itineraries.
    Returns count of refreshed bookings.

    Cron (GoDaddy cPanel):
    0 */6 * * * python -c "
    import sys; sys.path.insert(0, '/path/to/app')
    from app import create_app
    app = create_app('production')
    with app.app_context():
        from app.itinerary.refresh import refresh_upcoming_itineraries
        refresh_upcoming_itineraries()
    "
    """
    from app.models import Booking, Timeslot
    from app.itinerary.generator import generate_itinerary
    from app.itinerary.storage import save_itinerary

    now          = datetime.now(timezone.utc)
    refresh_from = now + timedelta(hours=46)
    refresh_to   = now + timedelta(hours=50)

    # Find bookings whose timeslot falls in the 46-50 hour window
    from app.extensions import db

    upcoming = (
        Booking.query
        .join(Timeslot, Booking.timeslot_id == Timeslot.timeslot_id)
        .filter(
            Booking.booking_status == 'confirmed',
        )
        .all()
    )

    # Filter in Python since combining Date+Time columns varies by DB
    to_refresh = []
    for b in upcoming:
        slot = b.timeslot
        if slot and slot.slot_date and slot.start_time:
            slot_dt = datetime.combine(slot.slot_date, slot.start_time).replace(
                tzinfo=timezone.utc)
            if refresh_from <= slot_dt <= refresh_to:
                to_refresh.append(b)

    refreshed = 0
    for booking in to_refresh:
        try:
            itinerary = generate_itinerary(booking)
            save_itinerary(booking.booking_id, itinerary, trigger='48hr_refresh')
            refreshed += 1
        except Exception as e:
            log.error(f'48hr refresh failed for {booking.booking_id}: {e}')

    log.info(f'48hr refresh: {refreshed} itineraries refreshed')
    return refreshed
