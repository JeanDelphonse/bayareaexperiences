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


# ── Audit log helper ──────────────────────────────────────────────────────────

def _log_provider(provider_id, action, field_name=None,
                  old_value=None, new_value=None, notes=None):
    from app.models import ProviderAuditLog
    from app.utils import generate_pk
    db.session.add(ProviderAuditLog(
        log_id        = generate_pk(),
        provider_id   = provider_id,
        admin_user_id = current_user.user_id,
        action        = action,
        field_name    = field_name,
        old_value     = old_value,
        new_value     = new_value,
        notes         = notes,
        created_at    = datetime.now(timezone.utc),
    ))


# ── Provider List ─────────────────────────────────────────────────────────────

@admin_bp.route('/providers')
@login_required
@_admin_required
def admin_providers():
    from app.models import Provider
    providers = Provider.query.order_by(Provider.applied_at.desc()).all()
    return render_template('admin/providers/list.html', providers=providers)


# ── Provider Web Search (AJAX) ────────────────────────────────────────────────

_SEARCH_SYSTEM = """
You are a business research assistant for Bay Area Experiences,
a private tour and transportation marketplace.
Your job is to find real, currently operating businesses that
could become providers on the BAE platform.

For each business found, extract as much as possible:
  business_name  — official business name (required)
  contact_name   — owner or primary contact person's name
  email          — contact email address
  phone          — phone number, formatted (xxx) xxx-xxxx
  website        — full URL including https://
  description    — 2-3 sentence bio suitable for a marketplace listing.
                   Focus on what they offer, their style, and their
                   Bay Area expertise. First person ("We offer...").
  why_good_fit   — 1 sentence on why this business suits BAE's marketplace.

RULES:
  - Only include real, currently operating businesses.
  - Skip large national chains.
  - Prefer businesses with a named contact person.
  - If a field cannot be found, return null for that field.
  - Do NOT invent or guess any field — only return what you find.
  - Output ONLY a valid JSON array. No prose outside the array.
"""


@admin_bp.route('/providers/search')
@login_required
@_admin_required
def admin_provider_search():
    import anthropic, json, os, re as _re
    from flask import jsonify

    query       = request.args.get('q', '').strip()
    location    = request.args.get('location', 'Bay Area CA').strip()
    max_results = min(int(request.args.get('max', 10) or 10), 20)

    if not query:
        return jsonify({'error': 'Query is required'}), 400

    user_prompt = (
        f'Search the web for Bay Area Experiences provider candidates.\n\n'
        f'PROVIDER TYPE: {query}\n'
        f'LOCATION:      {location}\n'
        f'MAX RESULTS:   {max_results}\n\n'
        f'Search for businesses matching the provider type in {location}. '
        f'Use multiple searches to build a comprehensive list. '
        f'For each business, find their contact person, email, phone, '
        f'website, and enough detail to write a 2-3 sentence bio.\n\n'
        f'Return a JSON array of up to {max_results} businesses:\n'
        f'[{{\n'
        f'  "business_name": "...",\n'
        f'  "contact_name":  "...",\n'
        f'  "email":         "...",\n'
        f'  "phone":         "...",\n'
        f'  "website":       "...",\n'
        f'  "description":   "...",\n'
        f'  "why_good_fit":  "..."\n'
        f'}}]'
    )

    try:
        client   = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
        response = client.messages.create(
            model      = 'claude-sonnet-4-6',
            max_tokens = 4096,
            system     = _SEARCH_SYSTEM,
            tools      = [{'type': 'web_search_20250305', 'name': 'web_search'}],
            messages   = [{'role': 'user', 'content': user_prompt}],
        )

        raw = ''.join(
            block.text for block in response.content
            if hasattr(block, 'text')
        )
        clean = _re.sub(r'```(?:json)?', '', raw).strip()
        start = clean.find('[')
        end   = clean.rfind(']') + 1
        if start < 0:
            return jsonify([])

        businesses = json.loads(clean[start:end])

        seen, dedup = set(), []
        for biz in businesses:
            key = (biz.get('business_name') or '').lower().strip()
            if key and key not in seen:
                seen.add(key)
                dedup.append(biz)

        return jsonify(dedup[:max_results])

    except Exception as e:
        import logging
        logging.getLogger('admin').error('Provider search failed: %s', e)
        return jsonify({'error': 'Search failed. Try again.'}), 500


# ── Create Provider ───────────────────────────────────────────────────────────

@admin_bp.route('/providers/new', methods=['GET', 'POST'])
@login_required
@_admin_required
def admin_provider_new():
    from app.models import Provider, User
    from app.utils import generate_pk
    from flask_bcrypt import Bcrypt
    import secrets, re

    if request.method == 'GET':
        return render_template('admin/providers/new.html')

    email       = request.form.get('email', '').strip().lower()
    contact_raw = request.form.get('contact_name', '').strip()
    biz_name    = request.form.get('business_name', '').strip()

    if not email or not biz_name:
        flash('Business name and email are required.', 'danger')
        return render_template('admin/providers/new.html')

    # Find or create user
    user = User.query.filter_by(email=email).first()
    if not user:
        parts = contact_raw.split(' ', 1)
        first = parts[0] or 'Provider'
        last  = parts[1] if len(parts) > 1 else 'Account'
        bcrypt = Bcrypt()
        tmp_pw = secrets.token_urlsafe(16)
        user = User(
            user_id       = generate_pk(),
            first_name    = first,
            last_name     = last,
            email         = email,
            password_hash = bcrypt.generate_password_hash(tmp_pw).decode('utf-8'),
        )
        db.session.add(user)
        db.session.flush()

    # Check not already a provider
    existing = Provider.query.filter_by(user_id=user.user_id).first()
    if existing:
        flash(f'User {email} is already linked to provider "{existing.business_name}".', 'warning')
        return redirect(url_for('admin.admin_provider_edit', provider_id=existing.provider_id))

    # Generate unique slug from business name
    slug_base = re.sub(r'[^a-z0-9]+', '-', biz_name.lower()).strip('-')
    slug = slug_base
    counter = 1
    while Provider.query.filter_by(business_slug=slug).first():
        slug = f'{slug_base}-{counter}'
        counter += 1

    now  = datetime.now(timezone.utc)
    tier = request.form.get('tier', 'free')
    provider = Provider(
        provider_id          = generate_pk(),
        user_id              = user.user_id,
        business_name        = biz_name,
        business_slug        = slug,
        bio                  = request.form.get('description', '').strip() or None,
        phone                = request.form.get('phone', '').strip() or None,
        website              = request.form.get('website', '').strip() or None,
        tier                 = tier,
        commission_rate      = Decimal('5.00') if tier == 'pro' else Decimal('20.00'),
        stripe_account_id    = request.form.get('stripe_account_id', '').strip() or None,
        is_active            = request.form.get('is_active') == '1',
        is_verified          = request.form.get('is_verified') == '1',
        can_list_experiences = request.form.get('is_verified') == '1',
        admin_notes          = request.form.get('admin_notes', '').strip() or None,
        approved_at          = now,
        applied_at           = now,
    )

    override = request.form.get('performance_commission_rate', '').strip()
    if override:
        try:
            provider.performance_commission_rate = Decimal(override)
        except Exception:
            pass

    if provider.is_verified:
        provider.approved_at = now
        provider.approved_by = current_user.user_id

    db.session.add(provider)
    db.session.flush()
    _log_provider(provider.provider_id, 'created',
                  notes=f'Admin-created: {biz_name}')
    db.session.commit()

    flash(f'Provider "{biz_name}" created successfully.', 'success')
    return redirect(url_for('admin.admin_provider_edit', provider_id=provider.provider_id))


# ── Edit Provider ─────────────────────────────────────────────────────────────

@admin_bp.route('/providers/<provider_id>/edit', methods=['GET', 'POST'])
@login_required
@_admin_required
def admin_provider_edit(provider_id):
    from app.models import Provider, ProviderAuditLog

    provider  = Provider.query.get_or_404(provider_id)
    audit_log = (ProviderAuditLog.query
                 .filter_by(provider_id=provider_id)
                 .order_by(ProviderAuditLog.created_at.desc())
                 .limit(10).all())

    if request.method == 'GET':
        return render_template('admin/providers/form.html',
                               provider=provider, audit_log=audit_log)

    now           = datetime.now(timezone.utc)
    change_reason = request.form.get('change_reason', '').strip() or None

    def _update(field, new_val, old_val=None):
        old = str(old_val if old_val is not None else getattr(provider, field, ''))
        new = str(new_val) if new_val is not None else ''
        if old != new:
            _log_provider(provider_id, 'field_updated',
                          field_name=field, old_value=old, new_value=new, notes=change_reason)
            setattr(provider, field, new_val if new_val != '' else None)

    # Business fields
    biz_name = request.form.get('business_name', '').strip()
    if biz_name and biz_name != provider.business_name:
        _log_provider(provider_id, 'field_updated', field_name='business_name',
                      old_value=provider.business_name, new_value=biz_name, notes=change_reason)
        provider.business_name = biz_name

    _update('bio',              request.form.get('description', '').strip() or None)
    _update('phone',            request.form.get('phone', '').strip() or None)
    _update('website',          request.form.get('website', '').strip() or None)
    _update('stripe_account_id', request.form.get('stripe_account_id', '').strip() or None)
    _update('admin_notes',      request.form.get('admin_notes', '').strip() or None)

    # Update linked user email + name
    contact_raw = request.form.get('contact_name', '').strip()
    email_raw   = request.form.get('email', '').strip().lower()
    if provider.user:
        if email_raw and email_raw != provider.user.email:
            _log_provider(provider_id, 'field_updated', field_name='email',
                          old_value=provider.user.email, new_value=email_raw, notes=change_reason)
            provider.user.email = email_raw
        if contact_raw and contact_raw != provider.user.full_name:
            parts = contact_raw.split(' ', 1)
            provider.user.first_name = parts[0]
            provider.user.last_name  = parts[1] if len(parts) > 1 else ''

    # Tier change
    new_tier = request.form.get('tier', provider.tier)
    if new_tier != provider.tier:
        _log_provider(provider_id, 'tier_changed', field_name='tier',
                      old_value=provider.tier, new_value=new_tier, notes=change_reason)
        provider.tier            = new_tier
        provider.commission_rate = Decimal('5.00') if new_tier == 'pro' else Decimal('20.00')

    # Commission override
    override_raw = request.form.get('performance_commission_rate', '').strip()
    new_override = Decimal(override_raw) if override_raw else None
    if new_override != provider.performance_commission_rate:
        _log_provider(provider_id, 'commission_override', field_name='performance_commission_rate',
                      old_value=str(provider.performance_commission_rate),
                      new_value=str(new_override), notes=change_reason)
        provider.performance_commission_rate = new_override

    # Active toggle
    new_active = request.form.get('is_active') == '1'
    if new_active != provider.is_active:
        action = 'activated' if new_active else 'deactivated'
        _log_provider(provider_id, action, notes=change_reason)
        provider.is_active = new_active

    # Verified toggle
    new_verified = request.form.get('is_verified') == '1'
    if new_verified != provider.is_verified:
        action = 'verified' if new_verified else 'unverified'
        _log_provider(provider_id, action, notes=change_reason)
        provider.is_verified = new_verified
        if new_verified:
            provider.approved_at = now
            provider.approved_by = current_user.user_id

    provider.updated_at = now if hasattr(provider, 'updated_at') else None
    db.session.commit()
    flash('Provider updated successfully.', 'success')
    return redirect(url_for('admin.admin_provider_edit', provider_id=provider_id))


# ── Verify toggle ─────────────────────────────────────────────────────────────

@admin_bp.route('/providers/<provider_id>/verify', methods=['POST'])
@login_required
@_admin_required
def admin_provider_verify(provider_id):
    from app.models import Provider
    provider = Provider.query.get_or_404(provider_id)
    provider.is_verified = not provider.is_verified
    if provider.is_verified:
        provider.approved_at = datetime.now(timezone.utc)
        provider.approved_by = current_user.user_id
    action = 'verified' if provider.is_verified else 'unverified'
    _log_provider(provider_id, action,
                  notes=request.form.get('reason', 'Quick toggle'))
    db.session.commit()
    flash(f'Provider marked as {action}.', 'success')
    return redirect(request.referrer or url_for('admin.admin_providers'))


# ── Deactivate ────────────────────────────────────────────────────────────────

@admin_bp.route('/providers/<provider_id>/deactivate', methods=['POST'])
@login_required
@_admin_required
def admin_provider_deactivate(provider_id):
    from app.models import Provider
    provider = Provider.query.get_or_404(provider_id)
    provider.is_active = False
    _log_provider(provider_id, 'deactivated',
                  notes=request.form.get('reason', ''))
    db.session.commit()
    flash('Provider deactivated.', 'warning')
    return redirect(request.referrer or url_for('admin.admin_providers'))


# ── Send welcome email ────────────────────────────────────────────────────────

@admin_bp.route('/providers/<provider_id>/send-welcome', methods=['POST'])
@login_required
@_admin_required
def admin_provider_send_welcome(provider_id):
    from app.models import Provider
    from app.marketplace.email import send_provider_welcome
    provider = Provider.query.get_or_404(provider_id)
    send_provider_welcome(provider)
    _log_provider(provider_id, 'welcome_email_sent')
    db.session.commit()
    flash('Welcome email sent.', 'success')
    return redirect(request.referrer or url_for('admin.admin_provider_edit', provider_id=provider_id))


# ── Add credit balance ────────────────────────────────────────────────────────

@admin_bp.route('/providers/<provider_id>/add-credit', methods=['POST'])
@login_required
@_admin_required
def admin_provider_add_credit(provider_id):
    from app.models import Provider
    provider = Provider.query.get_or_404(provider_id)
    try:
        amount = Decimal(request.form.get('amount', '0').strip())
    except Exception:
        flash('Invalid amount.', 'danger')
        return redirect(url_for('admin.admin_provider_edit', provider_id=provider_id))

    if amount <= 0:
        flash('Amount must be greater than zero.', 'danger')
        return redirect(url_for('admin.admin_provider_edit', provider_id=provider_id))

    old_balance = provider.referral_credit_balance or Decimal('0.00')
    provider.referral_credit_balance = old_balance + amount
    reason = request.form.get('reason', '').strip() or None
    _log_provider(provider_id, 'credit_added',
                  field_name='referral_credit_balance',
                  old_value=str(old_balance),
                  new_value=str(provider.referral_credit_balance),
                  notes=reason)
    db.session.commit()
    flash(f'${amount:.2f} added to credit balance.', 'success')
    return redirect(url_for('admin.admin_provider_edit', provider_id=provider_id))


# ── Audit log page ────────────────────────────────────────────────────────────

@admin_bp.route('/providers/<provider_id>/audit')
@login_required
@_admin_required
def admin_provider_audit_log(provider_id):
    from app.models import Provider, ProviderAuditLog
    provider  = Provider.query.get_or_404(provider_id)
    audit_log = (ProviderAuditLog.query
                 .filter_by(provider_id=provider_id)
                 .order_by(ProviderAuditLog.created_at.desc())
                 .all())
    return render_template('admin/providers/audit.html',
                           provider=provider, audit_log=audit_log)


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
