"""Provider public routes — apply, onboarding, public profile."""
import os
import re
import stripe
from datetime import datetime, timezone
from flask import (render_template, redirect, url_for, flash, request,
                   current_app, abort)
from flask_login import login_required, current_user
from app.blueprints.providers import providers_bp
from app.blueprints.providers.forms import ProviderApplicationForm, ProviderDocUploadForm
from app.blueprints.providers.decorators import current_provider
from app.extensions import db
from app.utils import generate_pk, send_email


def _slugify(text):
    slug = text.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_-]+', '-', slug)
    slug = re.sub(r'^-+|-+$', '', slug)
    return slug[:100]


def _unique_slug(base):
    from app.models import Provider
    slug = _slugify(base)
    if not Provider.query.filter_by(business_slug=slug).first():
        return slug
    i = 2
    while Provider.query.filter_by(business_slug=f'{slug}-{i}').first():
        i += 1
    return f'{slug}-{i}'


# ── Apply ─────────────────────────────────────────────────────────────────────

@providers_bp.route('/providers/apply', methods=['GET', 'POST'])
def apply():
    # Redirect logged-in providers straight to their dashboard
    if current_user.is_authenticated and current_user.provider:
        return redirect(url_for('providers.onboarding_tier'))

    form = ProviderApplicationForm()
    if form.validate_on_submit():
        # Must be signed in to submit — send them to register/login first
        if not current_user.is_authenticated:
            flash('Please create an account or sign in to submit your provider application.', 'info')
            return redirect(url_for('auth.register', next=url_for('providers.apply')))
        from app.models import Provider
        slug = _unique_slug(form.business_name.data)
        provider = Provider(
            provider_id      = generate_pk(),
            user_id          = current_user.user_id,
            business_name    = form.business_name.data,
            business_slug    = slug,
            phone            = form.phone.data,
            bio              = form.bio.data,
            experience_types = form.experience_types.data,
            years_experience = form.years_experience.data,
            service_cities   = ','.join(form.service_cities.data),
            website          = form.website.data or None,
            instagram        = form.instagram.data or None,
            languages_spoken = form.languages_spoken.data or None,
            why_join         = form.why_join.data,
            tier             = 'free',
            is_active        = True,
            can_list_experiences = False,
        )
        db.session.add(provider)
        db.session.commit()

        # Email admin
        try:
            from app.extensions import mail as _mail
            body_html = (
                f'<p>A new provider has applied.</p>'
                f'<p><strong>Name:</strong> {current_user.first_name} {current_user.last_name}<br>'
                f'<strong>Email:</strong> {current_user.email}<br>'
                f'<strong>Business:</strong> {form.business_name.data}<br>'
                f'<strong>Slug:</strong> {slug}</p>'
                f'<p><strong>Why join:</strong><br>{form.why_join.data}</p>'
                f'<p>Review at: /admin/providers/{provider.provider_id}</p>'
            )
            send_email(
                _mail,
                subject=f'New Provider Application: {form.business_name.data}',
                recipients=[current_app.config['ADMIN_EMAIL']],
                body_html=body_html,
            )
        except Exception:
            pass

        flash('Application submitted! We will review it and be in touch within 2–3 business days.', 'success')
        return redirect(url_for('providers.onboarding_tier'))

    return render_template('providers/apply.html', form=form)


# ── Onboarding ────────────────────────────────────────────────────────────────

@providers_bp.route('/providers/onboarding/tier', methods=['GET', 'POST'])
@login_required
def onboarding_tier():
    p = current_user.provider
    if not p:
        return redirect(url_for('providers.apply'))

    if request.method == 'POST':
        chosen = request.form.get('tier', 'free')
        if chosen not in ('free', 'pro'):
            chosen = 'free'
        p.tier = chosen
        db.session.commit()
        return redirect(url_for('providers.onboarding_stripe'))

    return render_template('providers/onboarding_tier.html', provider=p)


@providers_bp.route('/providers/onboarding/stripe')
@login_required
def onboarding_stripe():
    p = current_user.provider
    if not p:
        return redirect(url_for('providers.apply'))

    stripe.api_key = current_app.config.get('STRIPE_SECRET_KEY', '')
    try:
        if not p.stripe_account_id:
            account = stripe.Account.create(
                type='express',
                email=current_user.email,
                capabilities={'transfers': {'requested': True}},
                metadata={'provider_id': p.provider_id},
            )
            p.stripe_account_id = account['id']
            db.session.commit()

        link = stripe.AccountLink.create(
            account=p.stripe_account_id,
            refresh_url=url_for('providers.onboarding_stripe', _external=True),
            return_url=url_for('providers.onboarding_stripe_return', _external=True),
            type='account_onboarding',
        )
        return redirect(link['url'])
    except stripe.error.StripeError as e:
        flash(f'Stripe error: {e.user_message}', 'danger')
        return redirect(url_for('providers.onboarding_tier'))


@providers_bp.route('/providers/onboarding/stripe/return')
@login_required
def onboarding_stripe_return():
    p = current_user.provider
    if not p:
        return redirect(url_for('providers.apply'))

    stripe.api_key = current_app.config.get('STRIPE_SECRET_KEY', '')
    try:
        account = stripe.Account.retrieve(p.stripe_account_id)
        if account.get('details_submitted'):
            p.stripe_onboarding_complete = True
            db.session.commit()
            flash('Stripe account connected! You can now upload verification documents.', 'success')
            return redirect(url_for('providers.onboarding_documents'))
    except Exception:
        pass

    flash('Stripe onboarding incomplete. Please try again.', 'warning')
    return redirect(url_for('providers.onboarding_stripe'))


@providers_bp.route('/providers/onboarding/documents', methods=['GET', 'POST'])
@login_required
def onboarding_documents():
    p = current_user.provider
    if not p:
        return redirect(url_for('providers.apply'))

    form = ProviderDocUploadForm()
    if form.validate_on_submit():
        _save_doc(p, form)
        flash('Document uploaded successfully.', 'success')
        return redirect(url_for('providers.onboarding_documents'))

    docs = p.verification_docs if p else []
    return render_template('providers/onboarding_documents.html',
                           provider=p, form=form, docs=docs)


@providers_bp.route('/providers/onboarding/complete')
@login_required
def onboarding_complete():
    p = current_user.provider
    return render_template('providers/onboarding_complete.html', provider=p)


def _save_doc(provider, form):
    from app.models import ProviderVerificationDoc
    file = form.doc_file.data
    docs_dir = os.path.join(current_app.instance_path, 'provider_docs', provider.provider_id)
    os.makedirs(docs_dir, exist_ok=True)
    filename = f"{generate_pk()}_{file.filename}"
    filepath = os.path.join(docs_dir, filename)
    file.save(filepath)

    expires_at = None
    if form.expires_at.data:
        try:
            from datetime import date
            expires_at = date.fromisoformat(form.expires_at.data)
        except ValueError:
            pass

    doc = ProviderVerificationDoc(
        doc_id            = generate_pk(),
        provider_id       = provider.provider_id,
        doc_type          = form.doc_type.data,
        file_path         = filepath,
        original_filename = file.filename,
        file_size         = os.path.getsize(filepath),
        expires_at        = expires_at,
    )
    db.session.add(doc)
    db.session.commit()


# ── Public Provider Profile ───────────────────────────────────────────────────

@providers_bp.route('/providers/<slug>')
def provider_profile(slug):
    from app.models import Provider, Experience
    provider = Provider.query.filter_by(business_slug=slug, is_active=True).first_or_404()
    experiences = (Experience.query
                   .filter_by(provider_id=provider.provider_id, listing_status='active', is_active=True)
                   .order_by(Experience.created_at.desc())
                   .all())
    return render_template('providers/provider_profile.html',
                           provider=provider, experiences=experiences)
