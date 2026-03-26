"""
app/staff/portal.py — Staff portal invite utilities.

Handles invite token generation and email dispatch for both
BAE StaffMember and provider ProviderStaffMember portal invites.
"""
import secrets
import threading
from datetime import datetime, timezone, timedelta

from flask import url_for, render_template, current_app

from app.extensions import db
from app.utils import send_email


def send_staff_portal_invite(staff_member, mail, provider=None):
    """
    Generate a 64-char invite token on `staff_member`, persist it, and
    send the setup email in a background thread.

    Works for both StaffMember (BAE staff) and ProviderStaffMember.
    `provider` is passed for provider staff so the email shows the business name.
    """
    from app.models import ProviderStaffMember

    token = secrets.token_hex(32)   # 64 hex chars
    expires = datetime.now(timezone.utc) + timedelta(days=7)

    staff_member.staff_portal_token = token
    staff_member.staff_portal_token_expires = expires
    if isinstance(staff_member, ProviderStaffMember):
        staff_member.can_login = True
    db.session.commit()

    # Resolve URL and render template while still in request context
    setup_url = url_for('staff_portal.portal_setup', token=token, _external=True)
    staff_name = staff_member.full_name
    staff_email = staff_member.email
    body_html = render_template(
        'staff/email_portal_invite.html',
        staff_name=staff_name,
        setup_url=setup_url,
        provider=provider,
    )

    _app = current_app._get_current_object()
    _mail = mail

    def _send():
        with _app.app_context():
            try:
                send_email(
                    _mail,
                    subject='You\'re invited to the Bay Area Experiences Staff Portal',
                    recipients=[staff_email],
                    body_html=body_html,
                )
            except Exception as e:
                _app.logger.error(f'Portal invite email failed for {staff_email}: {e}')

    threading.Thread(target=_send, daemon=True).start()
