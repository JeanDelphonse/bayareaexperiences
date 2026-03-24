"""Admin marketplace routes — provider review, revenue, payouts."""
from decimal import Decimal
from datetime import datetime, timezone
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.blueprints.admin import admin_bp
from app.extensions import db


def _admin_required(f):
    from functools import wraps
    from flask_login import current_user
    from flask import abort
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ── Provider List ─────────────────────────────────────────────────────────────

@admin_bp.route('/providers')
@login_required
@_admin_required
def admin_providers():
    from app.models import Provider
    page        = request.args.get('page', 1, type=int)
    status      = request.args.get('status', '')
    tier_filter = request.args.get('tier', '')

    q = Provider.query
    if status == 'pending':
        q = q.filter_by(can_list_experiences=False, is_active=True)
    elif status == 'active':
        q = q.filter_by(can_list_experiences=True, is_active=True)
    elif status == 'inactive':
        q = q.filter_by(is_active=False)
    if tier_filter:
        q = q.filter_by(tier=tier_filter)

    providers = q.order_by(Provider.applied_at.desc()).paginate(page=page, per_page=20)
    return render_template('admin/marketplace/providers.html',
                           providers=providers, status=status, tier_filter=tier_filter)


# ── Provider Detail / Review ──────────────────────────────────────────────────

@admin_bp.route('/providers/<provider_id>')
@login_required
@_admin_required
def admin_provider_detail(provider_id):
    from app.models import Provider, Experience, Booking
    provider = Provider.query.get_or_404(provider_id)
    experiences = Experience.query.filter_by(provider_id=provider_id).all()
    booking_count = (Booking.query
                     .join(Experience, Booking.experience_id == Experience.experience_id)
                     .filter(Experience.provider_id == provider_id,
                             Booking.booking_status == 'confirmed')
                     .count())
    return render_template('admin/marketplace/provider_detail.html',
                           provider=provider, experiences=experiences,
                           booking_count=booking_count)


@admin_bp.route('/providers/<provider_id>/approve', methods=['POST'])
@login_required
@_admin_required
def admin_provider_approve(provider_id):
    from app.models import Provider
    from app.utils import send_email
    from flask import current_app
    provider = Provider.query.get_or_404(provider_id)
    provider.can_list_experiences = True
    provider.approved_at = datetime.now(timezone.utc)
    provider.approved_by = current_user.user_id
    db.session.commit()

    try:
        send_email(
            to=provider.user.email,
            subject='Your Bay Area Experiences provider application is approved!',
            body=(
                f'Hi {provider.user.first_name},\n\n'
                'Great news! Your provider application has been approved.\n\n'
                'You can now log in to your Provider Dashboard and create your first experience listing.\n\n'
                'Get started: /provider/dashboard\n\n'
                'Bay Area Experiences'
            ),
        )
    except Exception:
        pass

    flash(f'{provider.business_name} approved.', 'success')
    return redirect(url_for('admin.admin_provider_detail', provider_id=provider_id))


@admin_bp.route('/providers/<provider_id>/reject', methods=['POST'])
@login_required
@_admin_required
def admin_provider_reject(provider_id):
    from app.models import Provider
    from app.utils import send_email
    provider = Provider.query.get_or_404(provider_id)
    reason = request.form.get('reason', '').strip()
    provider.can_list_experiences = False
    provider.is_active = False
    provider.rejection_reason = reason
    db.session.commit()

    try:
        send_email(
            to=provider.user.email,
            subject='Update on your Bay Area Experiences provider application',
            body=(
                f'Hi {provider.user.first_name},\n\n'
                'Thank you for applying to become a provider on Bay Area Experiences.\n\n'
                'After reviewing your application, we are unable to approve it at this time.\n\n'
                + (f'Reason: {reason}\n\n' if reason else '')
                + 'If you believe this is an error or would like to reapply, please contact us.\n\n'
                'Bay Area Experiences'
            ),
        )
    except Exception:
        pass

    flash(f'{provider.business_name} rejected.', 'warning')
    return redirect(url_for('admin.admin_providers'))


@admin_bp.route('/providers/<provider_id>/toggle', methods=['POST'])
@login_required
@_admin_required
def admin_provider_toggle(provider_id):
    from app.models import Provider
    provider = Provider.query.get_or_404(provider_id)
    provider.is_active = not provider.is_active
    db.session.commit()
    state = 'activated' if provider.is_active else 'deactivated'
    flash(f'{provider.business_name} {state}.', 'success')
    return redirect(url_for('admin.admin_provider_detail', provider_id=provider_id))


@admin_bp.route('/providers/<provider_id>/approve-experience/<exp_id>', methods=['POST'])
@login_required
@_admin_required
def admin_approve_experience(provider_id, exp_id):
    from app.models import Experience, Provider
    exp = Experience.query.filter_by(experience_id=exp_id, provider_id=provider_id).first_or_404()
    exp.listing_status = 'active'
    exp.is_active = True
    # Mark first listing approved on the provider
    provider = Provider.query.get(provider_id)
    if not provider.first_listing_approved:
        provider.first_listing_approved = True
    db.session.commit()
    flash(f'"{exp.name}" approved and live.', 'success')
    return redirect(url_for('admin.admin_provider_detail', provider_id=provider_id))


@admin_bp.route('/providers/<provider_id>/reject-experience/<exp_id>', methods=['POST'])
@login_required
@_admin_required
def admin_reject_experience(provider_id, exp_id):
    from app.models import Experience
    exp = Experience.query.filter_by(experience_id=exp_id, provider_id=provider_id).first_or_404()
    exp.listing_status = 'draft'
    exp.is_active = False
    db.session.commit()
    flash(f'"{exp.name}" rejected.', 'warning')
    return redirect(url_for('admin.admin_provider_detail', provider_id=provider_id))


# ── Marketplace Revenue ───────────────────────────────────────────────────────

@admin_bp.route('/marketplace/revenue')
@login_required
@_admin_required
def admin_marketplace_revenue():
    from app.models import ProviderPayout, Booking, Experience, Provider
    from sqlalchemy import func

    # Summary stats
    total_gmv = (db.session.query(func.sum(ProviderPayout.booking_amount))
                 .scalar() or Decimal('0.00'))
    total_platform_fees = (db.session.query(func.sum(ProviderPayout.platform_fee))
                           .scalar() or Decimal('0.00'))
    total_provider_payouts = (db.session.query(func.sum(ProviderPayout.provider_amount))
                              .scalar() or Decimal('0.00'))
    pending_transfers = (db.session.query(func.sum(ProviderPayout.provider_amount))
                         .filter_by(stripe_transfer_status='pending')
                         .scalar() or Decimal('0.00'))

    # By tier breakdown
    free_fees = (db.session.query(func.sum(ProviderPayout.platform_fee))
                 .filter_by(tier_at_time='free').scalar() or Decimal('0.00'))
    pro_fees = (db.session.query(func.sum(ProviderPayout.platform_fee))
                .filter_by(tier_at_time='pro').scalar() or Decimal('0.00'))

    # Recent payouts
    page = request.args.get('page', 1, type=int)
    payouts = (ProviderPayout.query
               .order_by(ProviderPayout.created_at.desc())
               .paginate(page=page, per_page=25))

    return render_template('admin/marketplace/revenue.html',
                           total_gmv=float(total_gmv),
                           total_platform_fees=float(total_platform_fees),
                           total_provider_payouts=float(total_provider_payouts),
                           pending_transfers=float(pending_transfers),
                           free_fees=float(free_fees),
                           pro_fees=float(pro_fees),
                           payouts=payouts)


# ── Pending Experience Review Queue ──────────────────────────────────────────

@admin_bp.route('/marketplace/review-queue')
@login_required
@_admin_required
def admin_review_queue():
    from app.models import Experience
    pending = (Experience.query
               .filter_by(listing_status='pending_review')
               .order_by(Experience.created_at.asc())
               .all())
    return render_template('admin/marketplace/review_queue.html', pending=pending)
