import os
from datetime import datetime, timezone, timedelta
from flask import render_template, redirect, url_for, request, abort, jsonify
from flask_login import current_user
from app.blueprints.reviews import reviews_bp
from app.extensions import db
from app.models import ReviewToken, ExperienceReview, Experience, ReviewVote, ReviewFlag
from app.utils import generate_pk


# ── Feedback form ──────────────────────────────────────────────────────────────

@reviews_bp.route('/feedback/<token>', methods=['GET', 'POST'])
def feedback_form(token):
    rt = ReviewToken.query.filter_by(token=token).first()
    if not rt:
        abort(404)
    if rt.is_used:
        return render_template('reviews/already_submitted.html', experience=rt.experience)
    if rt.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        return render_template('reviews/token_expired.html',
                               experience=rt.experience,
                               phone='(408) 831-2101')

    booking    = rt.booking
    experience = rt.experience

    if request.method == 'POST':
        return _process_submission(rt, booking, experience)

    prefill_rating = request.args.get('rating', type=int)
    if prefill_rating and not (1 <= prefill_rating <= 5):
        prefill_rating = None

    return render_template('reviews/feedback_form.html',
                           booking=booking,
                           experience=experience,
                           prefill_rating=prefill_rating,
                           errors=[])


def _process_submission(rt, booking, experience):
    star_rating = request.form.get('star_rating', type=int)
    best_moment = request.form.get('best_moment', '').strip()

    errors = []
    if not star_rating or not (1 <= star_rating <= 5):
        errors.append('Please select a star rating.')
    if len(best_moment) < 10:
        errors.append('Please write at least 10 characters about your best moment.')
    if len(best_moment) > 1000:
        errors.append('Your response must be 1000 characters or fewer.')
    if errors:
        return render_template('reviews/feedback_form.html',
                               booking=booking, experience=experience,
                               prefill_rating=star_rating, errors=errors)

    now = datetime.now(timezone.utc)
    if star_rating <= 2:
        status       = 'held'
        held_until   = now + timedelta(hours=int(os.environ.get('REVIEW_LOW_SCORE_HOLD_HOURS', 24)))
        published_at = None
    else:
        status       = 'published'
        held_until   = None
        published_at = now

    first  = booking.guest_first_name or (booking.user.first_name if booking.user else 'Guest')
    last_i = (booking.guest_last_name or (booking.user.last_name if booking.user else ''))[0:1].upper()
    display_name = f'{first} {last_i}.' if last_i else first

    review = ExperienceReview(
        review_id                  = generate_pk(),
        booking_id                 = booking.booking_id,
        experience_id              = experience.experience_id,
        user_id                    = booking.user_id,
        provider_id                = experience.provider_id,
        star_rating                = star_rating,
        best_moment                = best_moment,
        reviewer_first_name        = first,
        reviewer_last_name_initial = last_i,
        reviewer_display_name      = display_name,
        status                     = status,
        published_at               = published_at,
        held_until                 = held_until,
        feedback_token_id          = rt.token_id,
        ip_address                 = request.remote_addr,
    )
    db.session.add(review)

    rt.is_used = True
    rt.used_at = now

    if status == 'published':
        _update_experience_rating(experience.experience_id)

    db.session.commit()

    if status == 'held':
        try:
            from app.reviews.notifications import notify_admin_low_score
            notify_admin_low_score(review, booking, experience)
        except Exception:
            pass

    return redirect(url_for('reviews.thankyou', token=rt.token))


@reviews_bp.route('/feedback/<token>/thankyou')
def thankyou(token):
    rt = ReviewToken.query.filter_by(token=token).first_or_404()
    return render_template('reviews/thankyou.html', experience=rt.experience)


# ── AJAX: helpful vote ─────────────────────────────────────────────────────────

@reviews_bp.route('/reviews/<review_id>/helpful', methods=['POST'])
def helpful(review_id):
    review = ExperienceReview.query.filter_by(
        review_id=review_id, status='published').first_or_404()

    ip = request.remote_addr
    user_id = current_user.user_id if current_user.is_authenticated else None

    # Prevent duplicate votes
    existing = ReviewVote.query.filter_by(review_id=review_id, ip_address=ip).first()
    if existing:
        return jsonify({'ok': False, 'count': review.helpful_count})

    vote = ReviewVote(
        vote_id    = generate_pk(),
        review_id  = review_id,
        user_id    = user_id,
        ip_address = ip,
    )
    db.session.add(vote)
    review.helpful_count += 1
    db.session.commit()
    return jsonify({'ok': True, 'count': review.helpful_count})


# ── AJAX: flag review ──────────────────────────────────────────────────────────

@reviews_bp.route('/reviews/<review_id>/flag', methods=['POST'])
def flag_review(review_id):
    review = ExperienceReview.query.filter_by(
        review_id=review_id, status='published').first_or_404()

    ip      = request.remote_addr
    reason  = request.form.get('reason', 'other')
    user_id = current_user.user_id if current_user.is_authenticated else None

    flag = ReviewFlag(
        flag_id             = generate_pk(),
        review_id           = review_id,
        reported_by_user_id = user_id,
        reported_by_ip      = ip,
        reason              = reason if reason in ('fake', 'offensive', 'spam', 'irrelevant', 'other') else 'other',
    )
    db.session.add(flag)
    review.flag_count += 1

    # Auto-flag if 3+ reports
    if review.flag_count >= 3:
        review.status = 'flagged'

    db.session.commit()
    return jsonify({'ok': True})


# ── Helper ─────────────────────────────────────────────────────────────────────

def _update_experience_rating(experience_id):
    from sqlalchemy import func
    result = db.session.query(
        func.avg(ExperienceReview.star_rating).label('avg'),
        func.count(ExperienceReview.review_id).label('cnt'),
    ).filter(
        ExperienceReview.experience_id == experience_id,
        ExperienceReview.status == 'published',
    ).one()

    db.session.query(Experience).filter_by(experience_id=experience_id).update({
        'avg_star_rating': round(float(result.avg), 2) if result.avg else None,
        'review_count':    result.cnt,
    })
