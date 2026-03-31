"""Admin loyalty dashboard routes."""
from flask import render_template, redirect, url_for, flash, request, make_response
from app.blueprints.admin import admin_bp
from app.utils import admin_required
from app.extensions import db


@admin_bp.route('/loyalty')
@admin_required
def loyalty_overview():
    from app.models import VipCustomer, DiscountCode, DiscountRedemption, ReferralRedemption, User
    from sqlalchemy import func

    total_vip     = VipCustomer.query.count()
    active_vip    = VipCustomer.query.filter_by(status='active').count()
    discounts_used = VipCustomer.query.filter_by(status='discount_used').count()

    total_discount_value = db.session.query(
        func.sum(DiscountRedemption.discount_amount)).scalar() or 0

    total_ref_completions = db.session.query(
        func.sum(VipCustomer.total_referrals_completed)).scalar() or 0
    total_ref_sent = db.session.query(
        func.sum(VipCustomer.total_referrals_sent)).scalar() or 0
    total_credits_issued = db.session.query(
        func.sum(ReferralRedemption.referrer_credit_earned)).scalar() or 0
    total_credits_outstanding = db.session.query(
        func.sum(User.total_referral_credit_balance)).scalar() or 0

    recent_vips = (VipCustomer.query
                   .order_by(VipCustomer.vip_earned_at.desc())
                   .limit(10).all())

    return render_template('admin/loyalty_overview.html',
                           total_vip=total_vip,
                           active_vip=active_vip,
                           discounts_used=discounts_used,
                           total_discount_value=float(total_discount_value),
                           total_ref_completions=int(total_ref_completions),
                           total_ref_sent=int(total_ref_sent),
                           total_credits_issued=float(total_credits_issued),
                           total_credits_outstanding=float(total_credits_outstanding),
                           recent_vips=recent_vips)


@admin_bp.route('/loyalty/vip')
@admin_required
def loyalty_vip_list():
    from app.models import VipCustomer
    page = request.args.get('page', 1, type=int)
    vips = (VipCustomer.query
            .order_by(VipCustomer.vip_earned_at.desc())
            .paginate(page=page, per_page=50, error_out=False))
    return render_template('admin/loyalty_vip.html', vips=vips)


@admin_bp.route('/loyalty/referrals')
@admin_required
def loyalty_referrals():
    from app.models import ReferralRedemption
    page = request.args.get('page', 1, type=int)
    redemptions = (ReferralRedemption.query
                   .order_by(ReferralRedemption.referrer_credited_at.desc())
                   .paginate(page=page, per_page=50, error_out=False))
    return render_template('admin/loyalty_referrals.html', redemptions=redemptions)


@admin_bp.route('/loyalty/discounts')
@admin_required
def loyalty_discounts():
    from app.models import DiscountCode
    page = request.args.get('page', 1, type=int)
    codes = (DiscountCode.query
             .order_by(DiscountCode.created_at.desc())
             .paginate(page=page, per_page=50, error_out=False))
    return render_template('admin/loyalty_discounts.html', codes=codes)


@admin_bp.route('/loyalty/vip/<user_id>/grant', methods=['POST'])
@admin_required
def loyalty_grant_vip(user_id):
    """Admin manually grants VIP to a user."""
    from app.models import User, Booking, ExperienceReview
    from app.loyalty.codes import generate_vip_discount_code, generate_referral_code
    from app.models import VipCustomer
    from app.utils import generate_pk
    from datetime import datetime, timezone, timedelta
    import os

    user = User.query.get_or_404(user_id)
    # Find most recent confirmed booking for this user
    booking = (Booking.query.filter_by(user_id=user_id, booking_status='confirmed')
               .order_by(Booking.created_at.desc()).first())
    if not booking:
        flash('User has no confirmed booking to attach VIP status to.', 'danger')
        return redirect(url_for('admin.loyalty_vip_list'))

    # Create a synthetic review entry is not needed — use a placeholder approach
    # Just create VIP record directly without qualifying_review_id requirement
    # We'll use a dummy review by checking if we can create one or skip it
    # Actually the model requires qualifying_review_id — let's check for an existing review
    review = (ExperienceReview.query
              .filter_by(user_id=user_id)
              .order_by(ExperienceReview.created_at.desc()).first())

    if not review:
        flash('Cannot grant VIP: user has no reviews. Ask them to leave a review first.', 'danger')
        return redirect(url_for('admin.loyalty_vip_list'))

    existing = VipCustomer.query.filter_by(qualifying_review_id=review.review_id).first()
    if existing:
        flash('This review already has a VIP record attached.', 'warning')
        return redirect(url_for('admin.loyalty_vip_list'))

    now           = datetime.now(timezone.utc)
    discount_code = generate_vip_discount_code(user)
    db.session.add(discount_code)
    db.session.flush()

    vip = VipCustomer(
        vip_id                 = generate_pk(),
        user_id                = user_id,
        qualifying_review_id   = review.review_id,
        qualifying_booking_id  = booking.booking_id,
        status                 = 'active',
        discount_code_id       = discount_code.code_id,
        referral_code          = generate_referral_code(user),
        vip_earned_at          = now,
        discount_expires_at    = now + timedelta(days=int(os.environ.get('VIP_DISCOUNT_EXPIRY_DAYS', 365))),
    )
    db.session.add(vip)
    user.is_vip = True
    db.session.commit()

    try:
        from app.loyalty.email import send_vip_welcome_email
        send_vip_welcome_email(user, vip, discount_code)
    except Exception:
        pass

    flash(f'VIP status granted to {user.full_name}.', 'success')
    return redirect(url_for('admin.loyalty_vip_list'))


@admin_bp.route('/loyalty/vip/<user_id>/revoke', methods=['POST'])
@admin_required
def loyalty_revoke_vip(user_id):
    from app.models import User, VipCustomer, DiscountCode
    user = User.query.get_or_404(user_id)
    vips = VipCustomer.query.filter_by(user_id=user_id, status='active').all()
    for vip in vips:
        vip.status = 'expired'
        code = DiscountCode.query.get(vip.discount_code_id)
        if code:
            code.is_active = False
    user.is_vip = False
    db.session.commit()
    flash(f'VIP status revoked for {user.full_name}.', 'success')
    return redirect(url_for('admin.loyalty_vip_list'))


@admin_bp.route('/loyalty/discounts/<code_id>/deactivate', methods=['POST'])
@admin_required
def loyalty_deactivate_code(code_id):
    from app.models import DiscountCode
    code = DiscountCode.query.get_or_404(code_id)
    code.is_active = False
    db.session.commit()
    flash(f'Discount code {code.code} deactivated.', 'success')
    return redirect(url_for('admin.loyalty_discounts'))


@admin_bp.route('/loyalty/export')
@admin_required
def loyalty_export():
    """CSV export of VIP customers."""
    import csv, io
    from app.models import VipCustomer

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['user_id', 'name', 'email', 'status', 'referral_code',
                     'credit_balance', 'referrals_sent', 'referrals_completed',
                     'vip_earned_at', 'discount_expires_at'])
    for vip in VipCustomer.query.order_by(VipCustomer.vip_earned_at.desc()).all():
        writer.writerow([
            vip.user_id,
            vip.user.full_name,
            vip.user.email,
            vip.status,
            vip.referral_code,
            float(vip.referral_credit_balance),
            vip.total_referrals_sent,
            vip.total_referrals_completed,
            vip.vip_earned_at.strftime('%Y-%m-%d %H:%M'),
            vip.discount_expires_at.strftime('%Y-%m-%d'),
        ])
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = 'attachment; filename=bae_vip_export.csv'
    return response
