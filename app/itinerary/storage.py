"""Itinerary persistence — save and retrieve from booking_itineraries table."""
import json
import logging
from datetime import datetime, timezone

from app.extensions import db
from app.models import BookingItinerary
from app.utils import generate_pk

log = logging.getLogger('itinerary')


def save_itinerary(booking_id: str, itinerary: dict, trigger: str = 'booking_confirmed'):
    """
    Save a generated itinerary. Deactivates any existing active itinerary for
    this booking first, then inserts the new version.
    """
    try:
        # Deactivate old active version
        existing = BookingItinerary.query.filter_by(
            booking_id=booking_id, is_active=True).first()

        next_version = 1
        if existing:
            next_version = existing.version + 1
            existing.is_active = False

        local_events = itinerary.pop('local_events_raw', [])
        is_fallback  = itinerary.get('is_fallback', False)

        # Determine tour_date and pickup_city from the itinerary or booking
        from app.models import Booking
        booking = Booking.query.get(booking_id)
        tour_date   = booking.timeslot.slot_date if booking else None
        pickup_city = booking.pickup_city if booking else ''

        record = BookingItinerary(
            itinerary_id       = generate_pk(),
            booking_id         = booking_id,
            version            = next_version,
            is_active          = True,
            itinerary_json     = json.dumps(itinerary),
            pickup_city        = pickup_city,
            tour_date          = tour_date,
            local_events_found = len(local_events),
            ticketmaster_events = json.dumps(
                [e for e in local_events if e.get('source') == 'ticketmaster']),
            eventbrite_events   = json.dumps(
                [e for e in local_events if e.get('source') == 'eventbrite']),
            is_fallback        = is_fallback,
            generation_trigger = trigger,
            generated_at       = datetime.now(timezone.utc),
        )
        db.session.add(record)
        db.session.commit()
        log.info(f'Itinerary v{next_version} saved for booking {booking_id} (trigger={trigger})')
        return record

    except Exception as e:
        log.error(f'Failed to save itinerary for {booking_id}: {e}')
        db.session.rollback()
        return None


def get_active_itinerary(booking_id: str):
    """Return the active BookingItinerary record for a booking, or None."""
    return BookingItinerary.query.filter_by(
        booking_id=booking_id, is_active=True).first()


def get_itinerary_data(booking_id: str) -> dict | None:
    """Return the parsed itinerary dict for a booking, or None."""
    record = get_active_itinerary(booking_id)
    if not record:
        return None
    try:
        return json.loads(record.itinerary_json)
    except Exception:
        return None
