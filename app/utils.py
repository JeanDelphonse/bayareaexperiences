import secrets
import string
from functools import wraps
from flask import abort
from flask_login import current_user

ALPHABET = string.ascii_uppercase + string.digits  # A-Z 0-9 (36 chars)


def generate_pk(length: int = 9) -> str:
    """Generate a cryptographically random 9-char uppercase alphanumeric PK."""
    return ''.join(secrets.choice(ALPHABET) for _ in range(length))


def admin_required(f):
    """Decorator: require is_admin=True; return HTTP 403 otherwise."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def send_email(mail, subject, recipients, body_html, body_text=None):
    """Helper to send transactional emails via Flask-Mail."""
    from flask_mail import Message
    msg = Message(subject=subject, recipients=recipients, html=body_html, body=body_text or '')
    mail.send(msg)
