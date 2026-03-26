"""
app/blueprints/providers/staff.py — Provider staff management routes.

Routes (all under providers_bp, prefix /provider/dashboard/staff):
  GET       /provider/dashboard/staff                        — staff list
  GET/POST  /provider/dashboard/staff/new                    — add staff member
  GET/POST  /provider/dashboard/staff/<id>                   — edit staff member
  POST      /provider/dashboard/staff/<id>/deactivate        — deactivate
  POST      /provider/dashboard/staff/<id>/invite            — send portal invite
  POST      /provider/dashboard/staff/<id>/revoke-access     — revoke portal login

Also adds:
  GET       /provider/dashboard/bookings/<booking_id>        — booking detail with staff assignment
  POST      /provider/dashboard/bookings/<booking_id>/assign-staff — AJAX assign staff
"""
import threading

from flask import render_template, redirect, url_for, flash, request, jsonify, abort
from flask_login import login_required, current_user

from app.blueprints.providers import providers_bp
from app.blueprints.providers.decorators import provider_required, current_provider
from app.extensions import db
from app.utils import generate_pk, send_email

PROVIDER_STAFF_LIMIT_FREE = 5
LANGUAGES = ['English', 'Spanish', 'Mandarin', 'French', 'Portuguese', 'Other']


# ── Staff List ─────────────────────────────────────────────────────────────────

@providers_bp.route('/provider/dashboard/staff')
@login_required
@provider_required
def dashboard_staff():
    from app.models import ProviderStaffMember
    p = current_provider()
    staff = (ProviderStaffMember.query
             .filter_by(provider_id=p.provider_id)
             .order_by(ProviderStaffMember.created_at.asc())
             .all())
    active_count = sum(1 for s in staff if s.is_active)
    return render_template(
        'providers/dashboard/staff_list.html',
        provider=p,
        staff=staff,
        active_count=active_count,
        limit=PROVIDER_STAFF_LIMIT_FREE,
    )


# ── Add Staff ──────────────────────────────────────────────────────────────────

@providers_bp.route('/provider/dashboard/staff/new', methods=['GET', 'POST'])
@login_required
@provider_required
def dashboard_staff_new():
    from app.models import ProviderStaffMember
    p = current_provider()

    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name  = request.form.get('last_name',  '').strip()
        email      = request.form.get('email', '').strip().lower()
        title      = request.form.get('title', '').strip() or None
        phone      = request.form.get('phone', '').strip() or None
        languages  = ', '.join(request.form.getlist('languages')) or None
        bio        = request.form.get('bio', '').strip()[:300] or None
        notes      = request.form.get('notes', '').strip() or None
        send_invite = request.form.get('send_invite') == 'on'

        if not first_name or not last_name or not email:
            flash('First name, last name, and email are required.', 'danger')
            return render_template('providers/dashboard/staff_form.html',
                                   provider=p, member=None, languages=LANGUAGES)

        # Tier limit check (Free: 5 active staff)
        if p.tier == 'free':
            active = ProviderStaffMember.query.filter_by(
                provider_id=p.provider_id, is_active=True).count()
            if active >= PROVIDER_STAFF_LIMIT_FREE:
                flash('Free Tier allows up to 5 staff. Upgrade to Pro for unlimited staff.', 'danger')
                return redirect(url_for('providers.dashboard_staff'))

        # Duplicate email check within this provider's team
        existing = ProviderStaffMember.query.filter_by(
            provider_id=p.provider_id, email=email).first()
        if existing:
            flash('A staff member with that email already exists on your team.', 'danger')
            return render_template('providers/dashboard/staff_form.html',
                                   provider=p, member=None, languages=LANGUAGES)

        member = ProviderStaffMember(
            provider_staff_id=generate_pk(),
            provider_id=p.provider_id,
            first_name=first_name,
            last_name=last_name,
            full_name=f'{first_name} {last_name}',
            title=title,
            email=email,
            phone=phone,
            languages_spoken=languages,
            bio=bio,
            notes=notes,
        )
        db.session.add(member)
        db.session.commit()
        flash(f'{member.full_name} added to your team.', 'success')

        if send_invite:
            from app.extensions import mail as _mail
            from app.staff.portal import send_staff_portal_invite
            send_staff_portal_invite(member, _mail, provider=p)
            flash(f'Portal invite email sent to {email}.', 'info')

        return redirect(url_for('providers.dashboard_staff'))

    return render_template('providers/dashboard/staff_form.html',
                           provider=p, member=None, languages=LANGUAGES)


# ── Edit Staff ─────────────────────────────────────────────────────────────────

@providers_bp.route('/provider/dashboard/staff/<staff_id>', methods=['GET', 'POST'])
@login_required
@provider_required
def dashboard_staff_edit(staff_id):
    from app.models import ProviderStaffMember
    p = current_provider()
    member = ProviderStaffMember.query.filter_by(
        provider_staff_id=staff_id, provider_id=p.provider_id).first_or_404()

    if request.method == 'POST':
        member.first_name     = request.form.get('first_name', '').strip()
        member.last_name      = request.form.get('last_name',  '').strip()
        member.full_name      = f'{member.first_name} {member.last_name}'
        member.title          = request.form.get('title', '').strip() or None
        member.phone          = request.form.get('phone', '').strip() or None
        member.languages_spoken = ', '.join(request.form.getlist('languages')) or None
        member.bio            = request.form.get('bio', '').strip()[:300] or None
        member.notes          = request.form.get('notes', '').strip() or None
        new_email             = request.form.get('email', '').strip().lower()

        if new_email != member.email:
            dup = ProviderStaffMember.query.filter_by(
                provider_id=p.provider_id, email=new_email).first()
            if dup:
                flash('Another team member already has that email.', 'danger')
                return render_template('providers/dashboard/staff_form.html',
                                       provider=p, member=member, languages=LANGUAGES)
            member.email = new_email

        db.session.commit()
        flash(f'{member.full_name} updated.', 'success')
        return redirect(url_for('providers.dashboard_staff'))

    return render_template('providers/dashboard/staff_form.html',
                           provider=p, member=member, languages=LANGUAGES)


# ── Deactivate Staff ───────────────────────────────────────────────────────────

@providers_bp.route('/provider/dashboard/staff/<staff_id>/deactivate', methods=['POST'])
@login_required
@provider_required
def dashboard_staff_deactivate(staff_id):
    from app.models import ProviderStaffMember
    p = current_provider()
    member = ProviderStaffMember.query.filter_by(
        provider_staff_id=staff_id, provider_id=p.provider_id).first_or_404()
    member.is_active = False
    db.session.commit()
    flash(f'{member.full_name} has been deactivated.', 'success')
    return redirect(url_for('providers.dashboard_staff'))


# ── Send Portal Invite ─────────────────────────────────────────────────────────

@providers_bp.route('/provider/dashboard/staff/<staff_id>/invite', methods=['POST'])
@login_required
@provider_required
def dashboard_staff_invite(staff_id):
    from app.models import ProviderStaffMember
    from app.extensions import mail as _mail
    from app.staff.portal import send_staff_portal_invite
    p = current_provider()
    member = ProviderStaffMember.query.filter_by(
        provider_staff_id=staff_id, provider_id=p.provider_id).first_or_404()
    send_staff_portal_invite(member, _mail, provider=p)
    flash(f'Portal invite sent to {member.email}.', 'success')
    return redirect(url_for('providers.dashboard_staff'))


# ── Revoke Portal Access ───────────────────────────────────────────────────────

@providers_bp.route('/provider/dashboard/staff/<staff_id>/revoke-access', methods=['POST'])
@login_required
@provider_required
def dashboard_staff_revoke(staff_id):
    from app.models import ProviderStaffMember
    p = current_provider()
    member = ProviderStaffMember.query.filter_by(
        provider_staff_id=staff_id, provider_id=p.provider_id).first_or_404()
    member.can_login = False
    member.user_id   = None
    member.staff_portal_token = None
    member.staff_portal_token_expires = None
    db.session.commit()
    flash(f'Portal access revoked for {member.full_name}.', 'success')
    return redirect(url_for('providers.dashboard_staff'))


# ── Provider Booking Detail ────────────────────────────────────────────────────

@providers_bp.route('/provider/dashboard/bookings/<booking_id>')
@login_required
@provider_required
def dashboard_booking_detail(booking_id):
    from app.models import Booking, ProviderStaffMember
    p = current_provider()

    booking = (Booking.query
               .join(Booking.experience)
               .filter(Booking.booking_id == booking_id,
                       Booking.experience.has(provider_id=p.provider_id))
               .first_or_404())

    team = (ProviderStaffMember.query
            .filter_by(provider_id=p.provider_id, is_active=True)
            .order_by(ProviderStaffMember.full_name.asc())
            .all())

    assignment_logs = (booking.assignment_logs
                       if hasattr(booking, 'assignment_logs') else [])

    return render_template(
        'providers/dashboard/booking_detail.html',
        provider=p,
        booking=booking,
        team=team,
        assignment_logs=assignment_logs,
    )


# ── Provider Assign Staff (AJAX) ───────────────────────────────────────────────

@providers_bp.route('/provider/dashboard/bookings/<booking_id>/assign-staff', methods=['POST'])
@login_required
@provider_required
def provider_assign_staff(booking_id):
    from app.models import Booking, ProviderStaffMember, StaffAssignmentLog
    from app.extensions import mail as _mail

    p = current_provider()
    booking = (Booking.query
               .join(Booking.experience)
               .filter(Booking.booking_id == booking_id,
                       Booking.experience.has(provider_id=p.provider_id))
               .first_or_404())

    data = request.get_json(silent=True) or {}
    provider_staff_id = data.get('provider_staff_id') or ''
    reason = (data.get('reason') or '').strip() or None

    member = None
    if provider_staff_id:
        member = ProviderStaffMember.query.filter_by(
            provider_staff_id=provider_staff_id,
            provider_id=p.provider_id,
            is_active=True,
        ).first()
        if not member:
            return jsonify({'ok': False, 'error': 'Staff member not found'}), 400

    # Mutual exclusivity — clear BAE staff_id for provider bookings
    booking.staff_id = None

    # Log the change
    log = StaffAssignmentLog(
        log_id=generate_pk(),
        booking_id=booking_id,
        changed_by_user_id=current_user.user_id,
        changed_by_role='provider',
        previous_provider_staff_id=booking.provider_staff_id,
        new_provider_staff_id=provider_staff_id or None,
        reason=reason,
    )
    db.session.add(log)
    booking.provider_staff_id = provider_staff_id or None
    db.session.commit()

    # Notify staff member
    if member and member.email:
        _notify_provider_staff_assigned(booking, member, _mail)

    staff_name = member.full_name if member else 'Unassigned'
    return jsonify({'ok': True, 'staff_name': staff_name})


# ── Internal: Assignment Notification Email ────────────────────────────────────

def _notify_provider_staff_assigned(booking, member, mail):
    from flask import render_template, current_app
    try:
        body_html = render_template(
            'staff/email_assignment_notification.html',
            booking=booking,
            staff_name=member.full_name,
        )
        _app = current_app._get_current_object()
        _email = member.email
        _bid = booking.booking_id
        _m = mail

        def _send():
            with _app.app_context():
                try:
                    send_email(
                        _m,
                        subject=f'New Assignment: {booking.experience.name} — {booking.timeslot.slot_date}',
                        recipients=[_email],
                        body_html=body_html,
                    )
                except Exception as e:
                    _app.logger.error(f'Staff assignment email failed for booking {_bid}: {e}')

        threading.Thread(target=_send, daemon=True).start()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f'Failed to prepare assignment email: {e}')
