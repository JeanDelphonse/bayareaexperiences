import os
from flask_mail import Message
from app.extensions import mail


def notify_admin_low_score(review, booking, experience):
    """Email admin when a 1–2 star review is received."""
    admin_email = os.environ.get('ADMIN_EMAIL')
    if not admin_email:
        return

    try:
        from flask import url_for
        admin_review_url = url_for('admin.review_detail', review_id=review.review_id, _external=True)
    except Exception:
        admin_review_url = 'Check admin panel at /admin/reviews'

    msg = Message(
        subject=f'[BAE Review Alert] {review.star_rating}-star review received — {experience.name}',
        recipients=[admin_email],
        body=(
            f'A {review.star_rating}-star review was submitted for {experience.name}.\n\n'
            f'Reviewer: {review.reviewer_display_name}\n'
            f'Tour date: {booking.timeslot.slot_date}\n'
            f'Best moment response:\n"{review.best_moment}"\n\n'
            f'This review is HELD for 24 hours (auto-publishes at {review.held_until} UTC).\n'
            f'Review it at: {admin_review_url}\n\n'
            f'You may publish early, flag for review, or remove it from the admin panel.'
        )
    )
    try:
        mail.send(msg)
    except Exception as e:
        import logging
        logging.getLogger('reviews').error(f'Admin low-score notification failed: {e}')
