"""Provider dashboard routes — /provider/dashboard/*"""
import re
from decimal import Decimal
from datetime import datetime, timezone
from flask import (render_template, redirect, url_for, flash, request,
                   current_app, abort)
from flask_login import login_required, current_user
from app.blueprints.providers import providers_bp
from app.blueprints.providers.forms import ProviderExperienceForm, ProviderProfileForm, ProviderDocUploadForm
from app.blueprints.providers.decorators import provider_required, provider_active_required, current_provider
from app.extensions import db
from app.utils import generate_pk


def _slugify_exp(name):
    slug = name.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_-]+', '-', slug)
    slug = re.sub(r'^-+|-+$', '', slug)
    return slug[:190]


def _unique_exp_slug(name):
    from app.models import Experience
    base = _slugify_exp(name)
    if not Experience.query.filter_by(slug=base).first():
        return base
    i = 2
    while Experience.query.filter_by(slug=f'{base}-{i}').first():
        i += 1
    return f'{base}-{i}'


def _save_pickup_cities(exp, cities):
    from app.models import ExperiencePickupLocation
    ExperiencePickupLocation.query.filter_by(experience_id=exp.experience_id).delete()
    for city in cities:
        db.session.add(ExperiencePickupLocation(
            id=generate_pk(),
            experience_id=exp.experience_id,
            pickup_city=city,
        ))


def _get_pickup_cities(exp):
    return [loc.pickup_city for loc in exp.pickup_locations]


# ── Dashboard Overview ────────────────────────────────────────────────────────

@providers_bp.route('/provider/dashboard')
@login_required
@provider_required
def dashboard():
    from app.models import Experience, Booking, ProviderPayout
    p = current_provider()

    total_experiences = Experience.query.filter_by(provider_id=p.provider_id, is_active=True).count()
    total_bookings    = (Booking.query
                         .join(Experience, Booking.experience_id == Experience.experience_id)
                         .filter(Experience.provider_id == p.provider_id,
                                 Booking.booking_status == 'confirmed')
                         .count())
    total_earned = (db.session.query(db.func.sum(ProviderPayout.provider_amount))
                    .filter_by(provider_id=p.provider_id,
                               stripe_transfer_status='paid')
                    .scalar() or Decimal('0.00'))
    pending_payout = (db.session.query(db.func.sum(ProviderPayout.provider_amount))
                      .filter_by(provider_id=p.provider_id,
                                 stripe_transfer_status='pending')
                      .scalar() or Decimal('0.00'))

    recent_bookings = (Booking.query
                       .join(Experience, Booking.experience_id == Experience.experience_id)
                       .filter(Experience.provider_id == p.provider_id)
                       .order_by(Booking.created_at.desc())
                       .limit(5).all())

    return render_template('providers/dashboard/overview.html',
                           provider=p,
                           total_experiences=total_experiences,
                           total_bookings=total_bookings,
                           total_earned=float(total_earned),
                           pending_payout=float(pending_payout),
                           recent_bookings=recent_bookings)


# ── Experiences ───────────────────────────────────────────────────────────────

@providers_bp.route('/provider/dashboard/experiences')
@login_required
@provider_required                  # list visible to all active providers, approved or not
def dashboard_experiences():
    from app.models import Experience
    p = current_provider()
    experiences = (Experience.query
                   .filter_by(provider_id=p.provider_id)
                   .order_by(Experience.created_at.desc())
                   .all())
    limit_reached = p.can_list_experiences and len(experiences) >= p.experience_limit
    return render_template('providers/dashboard/experiences.html',
                           provider=p, experiences=experiences,
                           limit_reached=limit_reached)


@providers_bp.route('/provider/dashboard/experiences/new', methods=['GET', 'POST'])
@login_required
@provider_active_required
def dashboard_experience_new():
    from app.models import Experience
    p = current_provider()

    existing = Experience.query.filter_by(provider_id=p.provider_id).count()
    if existing >= p.experience_limit:
        flash(f'You have reached your {p.experience_limit}-experience limit. Upgrade to Pro for unlimited listings.', 'warning')
        return redirect(url_for('providers.dashboard_experiences'))

    form = ProviderExperienceForm()
    if request.method == 'POST' and not form.validate():
        flash('Please fix the errors below before saving.', 'danger')
    if form.validate_on_submit():
        exp = Experience(
            experience_id        = generate_pk(),
            slug                 = _unique_exp_slug(form.name.data),
            provider_id          = p.provider_id,
            name                 = form.name.data,
            short_description    = form.short_description.data,
            description          = form.description.data,
            category             = form.category.data,
            duration_hours       = float(form.duration_hours.data),
            price                = float(form.price.data),
            max_guests           = form.max_guests.data,
            inclusions           = form.inclusions.data,
            what_to_bring        = form.what_to_bring.data or None,
            cancellation_policy  = form.cancellation_policy.data,
            advance_booking_days = int(form.advance_booking_days.data),
            photo_url            = form.photo_url.data or None,
            is_active            = form.is_active.data,
            listing_status       = 'pending_review' if not p.first_listing_approved else 'active',
        )
        db.session.add(exp)
        db.session.flush()   # get experience_id before saving pickup cities
        _save_pickup_cities(exp, form.pickup_cities.data)
        db.session.commit()
        if exp.listing_status == 'pending_review':
            flash('Experience submitted for review. It will go live once approved.', 'info')
        else:
            flash('Experience listed successfully!', 'success')
        return redirect(url_for('providers.dashboard_experiences'))

    return render_template('providers/dashboard/experience_form.html',
                           provider=p, form=form, is_edit=False)


@providers_bp.route('/provider/dashboard/experiences/<exp_id>/edit', methods=['GET', 'POST'])
@login_required
@provider_active_required
def dashboard_experience_edit(exp_id):
    from app.models import Experience
    p = current_provider()
    exp = Experience.query.filter_by(experience_id=exp_id, provider_id=p.provider_id).first_or_404()

    form = ProviderExperienceForm(obj=exp)
    if request.method == 'POST' and not form.validate():
        flash('Please fix the errors below before saving.', 'danger')
    if form.validate_on_submit():
        exp.name                 = form.name.data
        exp.short_description    = form.short_description.data
        exp.description          = form.description.data
        exp.category             = form.category.data
        exp.duration_hours       = float(form.duration_hours.data)
        exp.price                = float(form.price.data)
        exp.max_guests           = form.max_guests.data
        exp.inclusions           = form.inclusions.data
        exp.what_to_bring        = form.what_to_bring.data or None
        exp.cancellation_policy  = form.cancellation_policy.data
        exp.advance_booking_days = int(form.advance_booking_days.data)
        exp.photo_url            = form.photo_url.data or None
        exp.is_active            = form.is_active.data
        _save_pickup_cities(exp, form.pickup_cities.data)
        db.session.commit()
        flash('Experience updated.', 'success')
        return redirect(url_for('providers.dashboard_experiences'))

    # Pre-fill pickup cities multi-select from related table
    if not form.pickup_cities.data:
        form.pickup_cities.data = _get_pickup_cities(exp)

    return render_template('providers/dashboard/experience_form.html',
                           provider=p, form=form, is_edit=True, experience=exp)


@providers_bp.route('/provider/dashboard/experiences/<exp_id>/toggle', methods=['POST'])
@login_required
@provider_required
def dashboard_experience_toggle(exp_id):
    from app.models import Experience
    p = current_provider()
    exp = Experience.query.filter_by(experience_id=exp_id, provider_id=p.provider_id).first_or_404()
    exp.is_active = not exp.is_active
    db.session.commit()
    state = 'activated' if exp.is_active else 'deactivated'
    flash(f'"{exp.name}" {state}.', 'success')
    return redirect(url_for('providers.dashboard_experiences'))


# ── Bookings ──────────────────────────────────────────────────────────────────

@providers_bp.route('/provider/dashboard/bookings')
@login_required
@provider_required
def dashboard_bookings():
    from app.models import Booking, Experience
    p = current_provider()
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')

    q = (Booking.query
         .join(Experience, Booking.experience_id == Experience.experience_id)
         .filter(Experience.provider_id == p.provider_id))
    if status_filter:
        q = q.filter(Booking.booking_status == status_filter)
    bookings = q.order_by(Booking.created_at.desc()).paginate(page=page, per_page=20)

    return render_template('providers/dashboard/bookings.html',
                           provider=p, bookings=bookings, status_filter=status_filter)


# ── Earnings ──────────────────────────────────────────────────────────────────

@providers_bp.route('/provider/dashboard/earnings')
@login_required
@provider_required
def dashboard_earnings():
    from app.models import ProviderPayout
    p = current_provider()
    page = request.args.get('page', 1, type=int)

    total_paid    = (db.session.query(db.func.sum(ProviderPayout.provider_amount))
                     .filter_by(provider_id=p.provider_id, stripe_transfer_status='paid')
                     .scalar() or Decimal('0.00'))
    total_pending = (db.session.query(db.func.sum(ProviderPayout.provider_amount))
                     .filter_by(provider_id=p.provider_id, stripe_transfer_status='pending')
                     .scalar() or Decimal('0.00'))

    payouts = (ProviderPayout.query
               .filter_by(provider_id=p.provider_id)
               .order_by(ProviderPayout.created_at.desc())
               .paginate(page=page, per_page=20))

    return render_template('providers/dashboard/earnings.html',
                           provider=p, payouts=payouts,
                           total_paid=float(total_paid),
                           total_pending=float(total_pending))


# ── Profile ───────────────────────────────────────────────────────────────────

@providers_bp.route('/provider/dashboard/profile', methods=['GET', 'POST'])
@login_required
@provider_required
def dashboard_profile():
    p = current_provider()
    form = ProviderProfileForm(obj=p)
    if form.validate_on_submit():
        p.business_name    = form.business_name.data
        p.bio              = form.bio.data
        p.website          = form.website.data or None
        p.instagram        = form.instagram.data or None
        p.languages_spoken = form.languages_spoken.data or None
        p.years_experience = form.years_experience.data
        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('providers.dashboard_profile'))
    return render_template('providers/dashboard/profile.html', provider=p, form=form)


# ── Subscription ──────────────────────────────────────────────────────────────

@providers_bp.route('/provider/dashboard/subscription')
@login_required
@provider_required
def dashboard_subscription():
    p = current_provider()
    return render_template('providers/dashboard/subscription.html', provider=p)


@providers_bp.route('/provider/dashboard/subscription/upgrade', methods=['POST'])
@login_required
@provider_required
def dashboard_subscription_upgrade():
    import stripe as stripe_lib
    p = current_provider()
    plan = request.form.get('plan', 'monthly')
    price_key = 'STRIPE_PRO_MONTHLY_PRICE_ID' if plan == 'monthly' else 'STRIPE_PRO_ANNUAL_PRICE_ID'
    price_id = current_app.config.get(price_key, '')
    if not price_id:
        flash('Subscription plans not configured yet.', 'danger')
        return redirect(url_for('providers.dashboard_subscription'))

    stripe_lib.api_key = current_app.config.get('STRIPE_SECRET_KEY', '')
    try:
        if not p.stripe_customer_id:
            customer = stripe_lib.Customer.create(
                email=current_user.email,
                name=p.business_name,
                metadata={'provider_id': p.provider_id},
            )
            p.stripe_customer_id = customer['id']
            db.session.commit()

        session = stripe_lib.checkout.Session.create(
            customer=p.stripe_customer_id,
            mode='subscription',
            line_items=[{'price': price_id, 'quantity': 1}],
            success_url=url_for('providers.dashboard_subscription', _external=True) + '?upgraded=1',
            cancel_url=url_for('providers.dashboard_subscription', _external=True),
            metadata={'provider_id': p.provider_id, 'plan': plan},
        )
        return redirect(session['url'])
    except stripe_lib.error.StripeError as e:
        flash(f'Stripe error: {e.user_message}', 'danger')
        return redirect(url_for('providers.dashboard_subscription'))


@providers_bp.route('/provider/dashboard/subscription/portal', methods=['POST'])
@login_required
@provider_required
def dashboard_subscription_portal():
    import stripe as stripe_lib
    p = current_provider()
    if not p.stripe_customer_id:
        flash('No billing account found.', 'danger')
        return redirect(url_for('providers.dashboard_subscription'))

    stripe_lib.api_key = current_app.config.get('STRIPE_SECRET_KEY', '')
    try:
        portal = stripe_lib.billing_portal.Session.create(
            customer=p.stripe_customer_id,
            return_url=url_for('providers.dashboard_subscription', _external=True),
        )
        return redirect(portal['url'])
    except stripe_lib.error.StripeError as e:
        flash(f'Stripe error: {e.user_message}', 'danger')
        return redirect(url_for('providers.dashboard_subscription'))


# ── Documents ─────────────────────────────────────────────────────────────────

@providers_bp.route('/provider/dashboard/documents', methods=['GET', 'POST'])
@login_required
@provider_required
def dashboard_documents():
    from app.blueprints.providers.views import _save_doc
    p = current_provider()
    form = ProviderDocUploadForm()
    if form.validate_on_submit():
        _save_doc(p, form)
        flash('Document uploaded.', 'success')
        return redirect(url_for('providers.dashboard_documents'))
    docs = p.verification_docs
    return render_template('providers/dashboard/documents.html',
                           provider=p, form=form, docs=docs)
