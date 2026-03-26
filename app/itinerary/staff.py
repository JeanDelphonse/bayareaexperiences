"""Midnight staff briefing email job."""
import logging
import os
from datetime import datetime, timezone, date

log = logging.getLogger('itinerary')


def send_staff_briefings():
    """
    Called by cron at 00:05 UTC each day.
    Sends briefing email to assigned staff/provider for every confirmed booking today.
    Returns count of emails sent.

    Cron (GoDaddy cPanel - runs at 12:05 AM daily):
    5 0 * * * python -c "
    import sys; sys.path.insert(0, '/path/to/app')
    from app import create_app
    app = create_app('production')
    with app.app_context():
        from app.itinerary.staff import send_staff_briefings
        send_staff_briefings()
    "
    """
    from app.models import Booking, Timeslot, BookingItinerary
    from app.extensions import db, mail
    from flask_mail import Message
    from flask import url_for

    today = date.today()

    bookings = (
        Booking.query
        .join(Timeslot, Booking.timeslot_id == Timeslot.timeslot_id)
        .filter(
            Booking.booking_status == 'confirmed',
            Timeslot.slot_date == today,
        )
        .all()
    )

    sent = 0
    for booking in bookings:
        recipient_email = None
        recipient_name  = 'Team'

        if booking.staff:
            recipient_email = booking.staff.email
            recipient_name  = booking.staff.full_name.split()[0]
        elif booking.experience.provider:
            recipient_email = booking.experience.provider.user.email
            recipient_name  = booking.experience.provider.business_name

        if not recipient_email:
            recipient_email = os.environ.get('ADMIN_EMAIL')

        if not recipient_email:
            continue

        try:
            briefing_url = url_for('itinerary.staff_briefing',
                                   booking_id=booking.booking_id,
                                   _external=True)

            msg = Message(
                subject=f'[BAE Today] {booking.experience.name} — {booking.pickup_city} pickup',
                recipients=[recipient_email],
            )
            msg.body = (
                f'Good morning {recipient_name},\n\n'
                f'You have a tour today:\n'
                f'  Experience: {booking.experience.name}\n'
                f'  Guest: {booking.guest_first_name} {booking.guest_last_name}'
                f' ({booking.guest_count} guest(s))\n'
                f'  Pickup: {booking.pickup_address or booking.pickup_city}\n'
                f'  Time: {booking.timeslot.start_time.strftime("%I:%M %p")}\n\n'
                f'Full briefing (mobile-optimized):\n{briefing_url}\n\n'
                f'Bay Area Experiences | (408) 831-2101'
            )
            mail.send(msg)

            itinerary_rec = BookingItinerary.query.filter_by(
                booking_id=booking.booking_id, is_active=True).first()
            if itinerary_rec:
                itinerary_rec.staff_notified_at = datetime.now(timezone.utc)
                db.session.commit()

            sent += 1
        except Exception as e:
            log.error(f'Staff briefing email failed for {booking.booking_id}: {e}')

    log.info(f'Staff briefings sent: {sent}')
    return sent
