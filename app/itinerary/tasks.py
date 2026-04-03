"""Async itinerary generation — background thread runner."""
import logging
import threading

log = logging.getLogger('itinerary')


def queue_itinerary_generation(booking_id: str, trigger: str = 'booking_confirmed'):
    """
    Run itinerary generation in a background daemon thread.
    Non-blocking — does not affect the HTTP response.
    For higher volume, replace threading with Celery or APScheduler.
    """
    from flask import current_app
    app = current_app._get_current_object()

    def _run():
        try:
            from app.models import Booking
            from app.itinerary.generator import generate_itinerary
            from app.itinerary.storage import save_itinerary
            from app.extensions import db

            with app.app_context():
                booking = Booking.query.get(booking_id)
                if not booking:
                    log.warning(f'queue_itinerary_generation: booking {booking_id} not found')
                    return
                itinerary = generate_itinerary(booking)
                # Release the DB connection before saving. generate_itinerary() holds
                # the session open during long Claude/Ticketmaster API calls, so MySQL
                # may have closed the connection by the time we get here.
                # If remove() itself fails (ROLLBACK over dead socket), SQLAlchemy has
                # already invalidated and discarded the dead connection — safe to ignore.
                try:
                    db.session.remove()
                except Exception as _e:
                    log.debug(f'db.session.remove() suppressed after long API call: {_e}')
                save_itinerary(booking_id, itinerary, trigger=trigger)
        except Exception as e:
            log.error(f'Background itinerary generation failed for {booking_id}: {e}', exc_info=True)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
