"""Loyalty blueprint — referral landing, VIP dashboard, guest claim."""
import os
from datetime import datetime, timezone
from flask import redirect, url_for, session as flask_session, render_template, flash, request, abort
from flask_login import login_required, current_user
from app.blueprints.loyalty import loyalty_bp
from app.extensions import db
from app.utils import generate_pk

LOYALTY_ENABLED = os.environ.get('LOYALTY_ENABLED', 'True').lower() not in ('false', '0', 'no')


# ── Referral landing ──────────────────────────────────────────────────────────

@loyalty_bp.route('/r/<referral_code>')
def referral_landing(referral_code):
    """Capture referral attribution in session and redirect to homepage."""
    if not LOYALTY_ENABLED:
        return redirect(url_for('main.index'))

    from app.models import VipCustomer, ReferralLink

    vip = VipCustomer.query.filter_by(referral_code=referral_code).first()
    if vip:
        ttl = int(os.environ.get('REFERRAL_SESSION_TTL_DAYS', 7)) * 24 * 3600
        flask_session['referral_code']      = referral_code
        flask_session['referral_referrer']  = vip.user.first_name
        flask_session['referral_expires']   = datetime.now(timezone.utc).timestamp() + ttl
        flask_session['referral_discount_pct'] = 10
        flask_session.modified = True

        # Log the click
        link = ReferralLink(
            link_id            = generate_pk(),
            referral_code      = referral_code,
            referrer_user_id   = vip.user_id,
            visitor_session_id = flask_session.get('tracking_session_id'),
            utm_medium         = request.args.get('utm_medium'),
            clicked_at         = datetime.now(timezone.utc),
        )
        db.session.add(link)
        vip.total_referrals_sent += 1
        db.session.commit()

    return redirect(url_for('main.index'))


@loyalty_bp.route('/r/<referral_code>/preview')
def referral_preview(referral_code):
    """Social preview page for shared referral links."""
    vip = VipCustomer.query.filter_by(referral_code=referral_code).first_or_404()
    base_url = os.environ.get('BASE_URL', 'https://bayareaexperiences.com')
    referral_url = f"{base_url}/r/{referral_code}"
    return render_template('loyalty/referral_preview.html', vip=vip, referral_url=referral_url)


# ── Customer VIP dashboard ────────────────────────────────────────────────────

@loyalty_bp.route('/account/vip')
@login_required
def vip_dashboard():
    if not LOYALTY_ENABLED:
        abort(404)
    if not current_user.is_vip:
        flash('You have not yet earned VIP status. Leave a 5-star review after your next tour!', 'info')
        return redirect(url_for('account.bookings'))

    from app.models import VipCustomer, DiscountRedemption, ReferralRedemption

    # Most recent active VIP record (or most recent overall)
    vip = (VipCustomer.query
           .filter_by(user_id=current_user.user_id, status='active')
           .order_by(VipCustomer.vip_earned_at.desc())
           .first())
    if not vip:
        vip = (VipCustomer.query
               .filter_by(user_id=current_user.user_id)
               .order_by(VipCustomer.vip_earned_at.desc())
               .first())

    redemption = None
    if vip and vip.status == 'discount_used':
        redemption = DiscountRedemption.query.filter_by(
            code_id=vip.discount_code_id).first()

    referral_history = (ReferralRedemption.query
                        .filter_by(referrer_user_id=current_user.user_id)
                        .order_by(ReferralRedemption.referrer_credited_at.desc())
                        .limit(20).all())

    base_url     = os.environ.get('BASE_URL', 'https://bayareaexperiences.com')
    referral_url = f"{base_url}/r/{vip.referral_code}" if vip else ''

    return render_template('account/vip.html',
                           vip=vip,
                           redemption=redemption,
                           referral_history=referral_history,
                           referral_url=referral_url)


# ── Guest VIP claim (after registration) ─────────────────────────────────────

@loyalty_bp.route('/loyalty/claim')
@login_required
def loyalty_claim():
    """
    Called after a guest reviewer creates an account.
    Links any pending 5-star review to the new user and grants VIP retroactively.
    """
    if not LOYALTY_ENABLED:
        return redirect(url_for('account.bookings'))

    from app.models import ExperienceReview, Booking

    # Find a published 5-star review matching this user's email with no user_id attached
    review = (ExperienceReview.query
              .join(Booking, ExperienceReview.booking_id == Booking.booking_id)
              .filter(
                  ExperienceReview.star_rating == 5,
                  ExperienceReview.status == 'published',
                  ExperienceReview.user_id == None,  # noqa: E711
                  Booking.guest_email == current_user.email,
              )
              .order_by(ExperienceReview.published_at.desc())
              .first())

    if not review:
        flash('No qualifying 5-star review found for this account.', 'info')
        return redirect(url_for('account.bookings'))

    # Attach review to this user account
    review.user_id = current_user.user_id
    db.session.commit()

    # Grant VIP
    from app.loyalty.vip import maybe_grant_vip
    booking = review.booking
    granted = maybe_grant_vip(review, booking)

    if granted:
        flash('Welcome to VIP status! Your 15% discount and referral link are ready.', 'success')
        return redirect(url_for('loyalty.vip_dashboard'))
    else:
        flash('VIP status could not be granted at this time. Please contact us.', 'warning')
        return redirect(url_for('account.bookings'))
