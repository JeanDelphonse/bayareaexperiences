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
    def _run():
        try:
            from app import create_app
            from app.models import Booking
            from app.itinerary.generator import generate_itinerary
            from app.itinerary.storage import save_itinerary

            app = create_app('production')
            with app.app_context():
                booking = Booking.query.get(booking_id)
                if not booking:
                    log.warning(f'queue_itinerary_generation: booking {booking_id} not found')
                    return
                itinerary = generate_itinerary(booking)
                save_itinerary(booking_id, itinerary, trigger=trigger)
        except Exception as e:
            log.error(f'Background itinerary generation failed for {booking_id}: {e}')

    t = threading.Thread(target=_run, daemon=True)
    t.start()
