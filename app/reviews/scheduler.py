import os
import secrets
from datetime import datetime, timezone, timedelta
from app.models import Booking, Timeslot, ReviewToken, ExperienceReview, Experience
from app.extensions import db
from app.utils import generate_pk


def process_pending_feedback_requests():
    """
    Called every 30 minutes.
    Finds completed bookings whose timeslot ended 3+ hours ago
    and where no feedback token has been sent yet.
    """
    if not os.environ.get('REVIEWS_ENABLED', 'True').lower() in ('1', 'true', 'yes'):
        return 0

    delay_hours = int(os.environ.get('FEEDBACK_EMAIL_DELAY_HOURS', 3))
    expiry_days = int(os.environ.get('REVIEW_TOKEN_EXPIRY_DAYS', 30))

    now     = datetime.now(timezone.utc)
    cutoff  = now - timedelta(hours=delay_hours)
    max_age = now - timedelta(days=7)

    cutoff_date  = (now - timedelta(hours=delay_hours)).date()
    max_age_date = (now - timedelta(days=7)).date()

    eligible = (
        Booking.query
        .join(Timeslot, Booking.timeslot_id == Timeslot.timeslot_id)
        .filter(
            Booking.booking_status == 'confirmed',
            Timeslot.slot_date <= cutoff_date,
            Timeslot.slot_date >= max_age_date,
            ~Booking.review_tokens.any(),
        )
        .all()
    )

    sent = 0
    for booking in eligible:
        token_str = secrets.token_hex(32)
        expires   = now + timedelta(days=expiry_days)

        token = ReviewToken(
            token_id      = generate_pk(),
            token         = token_str,
            booking_id    = booking.booking_id,
            experience_id = booking.experience_id,
            user_id       = booking.user_id,
            email_sent_to = booking.guest_email or (booking.user.email if booking.user else ''),
            expires_at    = expires,
        )
        db.session.add(token)
        db.session.flush()

        try:
            from app.reviews.email import send_feedback_request
            success = send_feedback_request(booking, token)
            if success:
                token.email_sent_at = now
                sent += 1
        except Exception as e:
            import logging
            logging.getLogger('reviews').error(f'Feedback email failed for booking {booking.booking_id}: {e}')

    db.session.commit()
    return sent


def auto_publish_held_reviews():
    """Publish any held reviews whose 24-hour window has passed."""
    from app.blueprints.reviews.views import _update_experience_rating

    now  = datetime.now(timezone.utc)
    held = ExperienceReview.query.filter(
        ExperienceReview.status == 'held',
        ExperienceReview.held_until <= now,
    ).all()

    for review in held:
        review.status       = 'published'
        review.published_at = now
        _update_experience_rating(review.experience_id)

    db.session.commit()
    return len(held)
