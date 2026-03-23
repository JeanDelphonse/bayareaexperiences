import os
import threading
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, TelField
from wtforms.validators import DataRequired, Email, Length, Optional
from app.blueprints.contact import contact_bp
from app.extensions import db, mail, limiter
from app.models import ContactSubmission
from app.utils import generate_pk

SUBJECT_CHOICES = [
    ('', '— Select a subject —'),
    ('General Inquiry',               'General Inquiry'),
    ('Booking Question',              'Booking Question'),
    ('Custom / Private Experience',   'Custom / Private Experience'),
    ('Corporate Team Outing',         'Corporate Team Outing'),
    ('Celebration Package',           'Celebration Package'),
    ('Airport or Cruise Transfer',    'Airport or Cruise Transfer'),
    ('Pricing Information',           'Pricing Information'),
    ('Feedback or Compliment',        'Feedback or Compliment'),
    ('Other',                         'Other'),
]

REFERRAL_CHOICES = [
    ('', '— How did you hear about us? —'),
    ('Google Search',           'Google Search'),
    ('Instagram',               'Instagram'),
    ('TikTok',                  'TikTok'),
    ('Friend or Family Referral', 'Friend or Family Referral'),
    ('Hotel Concierge',         'Hotel Concierge'),
    ('Viator / TripAdvisor',    'Viator / TripAdvisor'),
    ('Other',                   'Other'),
]


class ContactForm(FlaskForm):
    full_name       = StringField('Full Name',   validators=[DataRequired(), Length(min=2, max=100)])
    visitor_email   = StringField('Email',       validators=[DataRequired(), Email(), Length(max=150)])
    phone           = TelField('Phone',          validators=[Optional(), Length(max=20)])
    subject         = SelectField('Subject',     choices=SUBJECT_CHOICES, validators=[DataRequired()])
    message         = TextAreaField('Message',   validators=[DataRequired(), Length(min=10, max=2000)])
    referral_source = SelectField('How did you hear about us?',
                                  choices=REFERRAL_CHOICES, validators=[Optional()])


@contact_bp.route('/', methods=['GET', 'POST'])
@limiter.limit("5 per hour", methods=['POST'])
def contact():
    # Pre-fill subject from ?subject= query param
    subject_prefill = request.args.get('subject', '')
    form = ContactForm()
    if request.method == 'GET' and subject_prefill:
        matching = [v for v, _ in SUBJECT_CHOICES if v == subject_prefill]
        if matching:
            form.subject.data = matching[0]

    if form.validate_on_submit():
        sub = ContactSubmission(
            submission_id=generate_pk(),
            full_name=form.full_name.data.strip(),
            visitor_email=form.visitor_email.data.strip().lower(),
            phone=form.phone.data.strip() if form.phone.data else None,
            subject=form.subject.data,
            message=form.message.data.strip(),
            referral_source=form.referral_source.data or None,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string[:500] if request.user_agent.string else None,
        )
        db.session.add(sub)
        db.session.commit()

        # Send notifications in background so the request returns immediately
        app = current_app._get_current_object()
        submission_id = sub.submission_id
        threading.Thread(
            target=_notify_admin,
            args=(app, submission_id),
            daemon=True,
        ).start()

        flash(
            "Your message has been sent! We\u2019ll be in touch within 2\u20134 hours. "
            "You can also reach us directly at "
            "<a href=\"tel:+14088312101\" class=\"alert-link\">(408) 831-2101</a>.",
            'success'
        )
        return redirect(url_for('contact.contact'))

    return render_template('contact/contact.html', form=form)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _notify_admin(app, submission_id):
    """Run in a background thread — send email + SMS then update flags."""
    with app.app_context():
        sub = ContactSubmission.query.get(submission_id)
        if not sub:
            return
        sub.email_sent = _send_admin_email(app, sub)
        sub.sms_sent   = _send_admin_sms(app, sub)
        db.session.commit()


def _send_admin_email(app, sub):
    try:
        from flask_mail import Message
        admin_email = app.config.get('ADMIN_EMAIL', 'valuemanager.management@gmail.com')
        msg = Message(
            subject=f'[BAE Contact] {sub.subject} \u2014 {sub.full_name}',
            recipients=[admin_email],
            reply_to=sub.visitor_email,
            extra_headers={'X-Priority': '1'},
        )
        msg.html = render_template('email/contact_admin.html', sub=sub)
        msg.body = render_template('email/contact_admin.txt', sub=sub)
        mail.send(msg)
        return True
    except Exception as exc:
        app.logger.error(f'Contact email failed: {exc}')
        return False


def _send_admin_sms(app, sub):
    sid      = os.environ.get('TWILIO_ACCOUNT_SID')
    token    = os.environ.get('TWILIO_AUTH_TOKEN')
    from_num = os.environ.get('TWILIO_FROM_NUMBER')
    to_num   = os.environ.get('TWILIO_TO_NUMBER', '+14088312101')

    if not all([sid, token, from_num]):
        return False

    try:
        from twilio.rest import Client
        client = Client(sid, token)
        body = (
            f'[BAE Contact] {sub.subject}\n'
            f'From: {sub.full_name} ({sub.visitor_email})\n'
            f'{sub.phone or "no phone"}\n'
            f'ID: {sub.submission_id}'
        )
        client.messages.create(body=body, from_=from_num, to=to_num)
        return True
    except Exception as exc:
        app.logger.error(f'Contact SMS failed: {exc}')
        return False
