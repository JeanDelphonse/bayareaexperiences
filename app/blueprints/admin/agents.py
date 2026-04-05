"""Admin agent control panel — /admin/agents/*"""
import json
import threading
from datetime import datetime, timezone

from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user

from app.blueprints.admin import admin_bp
from app.extensions import db
from app.utils import admin_required, generate_pk

AGENT_META = {
    'BAE-AGENT-SOCIAL':  {'label': 'Social Media',    'icon': 'bi-instagram',       'color': '#E1306C'},
    'BAE-AGENT-ADS':     {'label': 'Google Ads',      'icon': 'bi-google',          'color': '#4285F4'},
    'BAE-AGENT-EMAIL':   {'label': 'Email & Loyalty', 'icon': 'bi-envelope-fill',   'color': '#0d6efd'},
    'BAE-AGENT-PARTNER': {'label': 'Partnerships',    'icon': 'bi-building',        'color': '#198754'},
    'BAE-AGENT-MYSTERY': {'label': 'Mystery Tour',    'icon': 'bi-question-diamond','color': '#6f42c1'},
}


def _get_agent(code: str):
    """Return an instantiated agent by code."""
    from app.agents.social.agent  import SocialMediaAgent
    from app.agents.ads.agent     import GoogleAdsAgent
    from app.agents.email.agent   import EmailLoyaltyAgent
    from app.agents.partner.agent import PartnershipAgent
    from app.agents.mystery.agent import MysteryTourAgent
    return {
        'BAE-AGENT-SOCIAL':  SocialMediaAgent,
        'BAE-AGENT-ADS':     GoogleAdsAgent,
        'BAE-AGENT-EMAIL':   EmailLoyaltyAgent,
        'BAE-AGENT-PARTNER': PartnershipAgent,
        'BAE-AGENT-MYSTERY': MysteryTourAgent,
    }.get(code, lambda: None)()


def _run_agent_async(code: str, context: dict = None):
    """Run an agent in a background thread."""
    from flask import current_app
    app = current_app._get_current_object()

    def _worker():
        with app.app_context():
            agent = _get_agent(code)
            if agent:
                agent.run(trigger_type='manual', context=context or {})
    t = threading.Thread(target=_worker, daemon=True)
    t.start()


# ── Control Panel ─────────────────────────────────────────────────────────────

@admin_bp.route('/agents')
@login_required
@admin_required
def agents_dashboard():
    from app.models import AgentRun
    cards = []
    for code, meta in AGENT_META.items():
        last_run   = (AgentRun.query.filter_by(agent_code=code)
                      .order_by(AgentRun.created_at.desc()).first())
        pending    = (AgentRun.query.filter_by(agent_code=code, status='pending_approval')
                      .count())
        last_failed= (last_run and last_run.status == 'failed')
        cards.append({
            'code':       code,
            'meta':       meta,
            'last_run':   last_run,
            'pending':    pending,
            'last_failed':last_failed,
        })
    total_pending = AgentRun.query.filter_by(status='pending_approval').count()
    return render_template('admin/agents/index.html',
                           cards=cards, total_pending=total_pending, agent_meta=AGENT_META)


# ── Approval Queue ────────────────────────────────────────────────────────────

@admin_bp.route('/agents/queue')
@login_required
@admin_required
def agents_queue():
    from app.models import AgentRun
    agent_filter = request.args.get('agent', '')
    q = AgentRun.query.filter_by(status='pending_approval')
    if agent_filter:
        q = q.filter_by(agent_code=agent_filter)
    runs = q.order_by(AgentRun.created_at.asc()).all()
    return render_template('admin/agents/queue.html',
                           runs=runs, agent_meta=AGENT_META,
                           agent_filter=agent_filter)


@admin_bp.route('/agents/queue/<run_id>/approve', methods=['POST'])
@login_required
@admin_required
def agents_approve(run_id):
    from app.models import AgentRun
    run = AgentRun.query.get_or_404(run_id)
    if run.status != 'pending_approval':
        flash('This run is no longer pending.', 'warning')
        return redirect(url_for('admin.agents_queue'))

    # Allow inline edit of draft before approving
    edited = request.form.get('output_draft')
    if edited:
        try:
            json.loads(edited)   # validate JSON
            run.output_draft = edited
        except ValueError:
            flash('Invalid JSON in edited draft — original used.', 'warning')

    run.status       = 'approved'
    run.admin_user_id= current_user.user_id
    run.approved_at  = datetime.now(timezone.utc)
    run.admin_notes  = request.form.get('notes', '')
    db.session.commit()

    # Trigger publish in background
    from flask import current_app
    app = current_app._get_current_object()
    draft = json.loads(run.output_draft or '{}')

    def _publish():
        with app.app_context():
            agent = _get_agent(run.agent_code)
            if agent:
                try:
                    agent.publish(draft, run)
                    run.status       = 'published'
                    run.published_at = datetime.now(timezone.utc)
                    db.session.commit()
                except Exception as e:
                    run.status      = 'failed'
                    run.admin_notes = (run.admin_notes or '') + f' | publish error: {e}'
                    db.session.commit()

    threading.Thread(target=_publish, daemon=True).start()
    flash('Draft approved — publishing in progress.', 'success')
    return redirect(url_for('admin.agents_queue'))


@admin_bp.route('/agents/queue/<run_id>/reject', methods=['POST'])
@login_required
@admin_required
def agents_reject(run_id):
    from app.models import AgentRun
    run = AgentRun.query.get_or_404(run_id)
    run.status        = 'rejected'
    run.admin_user_id = current_user.user_id
    run.admin_notes   = request.form.get('notes', '')
    run.approved_at   = datetime.now(timezone.utc)
    db.session.commit()
    flash('Draft rejected.', 'info')
    return redirect(url_for('admin.agents_queue'))


@admin_bp.route('/agents/queue/<run_id>/edit', methods=['POST'])
@login_required
@admin_required
def agents_edit_draft(run_id):
    from app.models import AgentRun
    run   = AgentRun.query.get_or_404(run_id)
    draft = request.get_json(force=True) or {}
    try:
        run.output_draft = json.dumps(draft)
        db.session.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


# ── Manual Trigger ────────────────────────────────────────────────────────────

@admin_bp.route('/agents/<code>/run', methods=['POST'])
@login_required
@admin_required
def agents_run_now(code):
    if code not in AGENT_META:
        flash('Unknown agent code.', 'danger')
        return redirect(url_for('admin.agents_dashboard'))
    context = {}
    try:
        body = request.get_json(silent=True) or {}
        context = body.get('context', {})
    except Exception:
        pass
    _run_agent_async(code, context)
    flash(f'{AGENT_META[code]["label"]} agent triggered — check the queue shortly.', 'success')
    return redirect(url_for('admin.agents_dashboard'))


# ── Run History ───────────────────────────────────────────────────────────────

@admin_bp.route('/agents/<code>/history')
@login_required
@admin_required
def agents_history(code):
    from app.models import AgentRun
    if code not in AGENT_META:
        flash('Unknown agent code.', 'danger')
        return redirect(url_for('admin.agents_dashboard'))
    page = request.args.get('page', 1, type=int)
    runs = (AgentRun.query.filter_by(agent_code=code)
            .order_by(AgentRun.created_at.desc())
            .paginate(page=page, per_page=20))
    return render_template('admin/agents/history.html',
                           code=code, meta=AGENT_META[code],
                           runs=runs, agent_meta=AGENT_META)


# ── Settings ──────────────────────────────────────────────────────────────────

@admin_bp.route('/agents/<code>/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def agents_settings(code):
    from app.models import AgentSetting
    if code not in AGENT_META:
        flash('Unknown agent code.', 'danger')
        return redirect(url_for('admin.agents_dashboard'))

    if request.method == 'POST':
        for key, value in request.form.items():
            if key.startswith('_'):
                continue
            row = AgentSetting.query.filter_by(agent_code=code, key=key).first()
            if row:
                row.value = json.dumps(value) if value not in ('true', 'false') else value
            else:
                db.session.add(AgentSetting(
                    setting_id = generate_pk(),
                    agent_code = code,
                    key        = key,
                    value      = json.dumps(value) if value not in ('true','false') else value,
                ))
        db.session.commit()
        flash('Settings saved.', 'success')
        return redirect(url_for('admin.agents_settings', code=code))

    settings = {s.key: s.value for s in
                AgentSetting.query.filter_by(agent_code=code).all()}
    return render_template('admin/agents/settings.html',
                           code=code, meta=AGENT_META[code],
                           settings=settings, agent_meta=AGENT_META)


# ── Mystery Tour Admin ────────────────────────────────────────────────────────

@admin_bp.route('/agents/mystery')
@login_required
@admin_required
def agents_mystery():
    from app.models import Booking, Experience, AgentRun
    upcoming = (Booking.query
                .join(Experience)
                .filter(Experience.is_mystery == True,
                        Booking.booking_status == 'confirmed')
                .order_by(Booking.created_at.desc())
                .limit(50).all())
    return render_template('admin/agents/mystery.html',
                           upcoming=upcoming, agent_meta=AGENT_META)


@admin_bp.route('/agents/mystery/<booking_id>/reveal', methods=['POST'])
@login_required
@admin_required
def agents_mystery_reveal(booking_id):
    from app.models import Booking
    booking = Booking.query.get_or_404(booking_id)
    if booking.mystery_reveal_sent_at:
        flash('Reveal already sent for this booking.', 'warning')
        return redirect(url_for('admin.agents_mystery'))
    from app.agents.mystery.agent import _trigger_mystery_reveal
    threading.Thread(
        target=lambda: _trigger_mystery_reveal(booking), daemon=True).start()
    flash('Reveal email triggered.', 'success')
    return redirect(url_for('admin.agents_mystery'))


# ── Partner CRM ───────────────────────────────────────────────────────────────

@admin_bp.route('/agents/partners')
@login_required
@admin_required
def agents_partners():
    from app.models import Partner
    status_filter = request.args.get('status', '')
    type_filter   = request.args.get('type', '')
    q = Partner.query
    if status_filter:
        q = q.filter_by(status=status_filter)
    if type_filter:
        q = q.filter_by(partner_type=type_filter)
    partners = q.order_by(Partner.next_followup_at.asc()).all()
    return render_template('admin/agents/partners.html',
                           partners=partners, agent_meta=AGENT_META,
                           status_filter=status_filter, type_filter=type_filter)


@admin_bp.route('/agents/partners/new', methods=['GET', 'POST'])
@login_required
@admin_required
def agents_partner_new():
    from app.models import Partner
    if request.method == 'POST':
        partner = Partner(
            partner_id    = generate_pk(),
            partner_type  = request.form['partner_type'],
            business_name = request.form['business_name'],
            contact_name  = request.form.get('contact_name') or None,
            contact_email = request.form.get('contact_email') or None,
            contact_phone = request.form.get('contact_phone') or None,
            location_city = request.form.get('location_city') or None,
            notes         = request.form.get('notes') or None,
            status        = 'prospect',
        )
        db.session.add(partner)
        db.session.commit()
        flash(f'Partner "{partner.business_name}" added.', 'success')
        return redirect(url_for('admin.agents_partners'))
    return render_template('admin/agents/partner_form.html', agent_meta=AGENT_META, partner=None)


@admin_bp.route('/agents/partners/<partner_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def agents_partner_edit(partner_id):
    from app.models import Partner
    partner = Partner.query.get_or_404(partner_id)
    if request.method == 'POST':
        partner.business_name = request.form['business_name']
        partner.contact_name  = request.form.get('contact_name') or None
        partner.contact_email = request.form.get('contact_email') or None
        partner.contact_phone = request.form.get('contact_phone') or None
        partner.location_city = request.form.get('location_city') or None
        partner.status        = request.form.get('status', partner.status)
        partner.notes         = request.form.get('notes') or None
        db.session.commit()
        flash('Partner updated.', 'success')
        return redirect(url_for('admin.agents_partners'))
    return render_template('admin/agents/partner_form.html',
                           agent_meta=AGENT_META, partner=partner)
