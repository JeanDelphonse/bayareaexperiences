import secrets
import string
from functools import wraps
from flask import abort
from flask_login import current_user

ALPHABET = string.ascii_uppercase + string.digits  # A-Z 0-9 (36 chars)

_ALLOWED_PAGE_SIZES = (10, 20, 50)


class PaginationResult:
    """Lightweight pagination result — drop-in compatible with Flask-SQLAlchemy's Pagination."""

    def __init__(self, items, page, per_page, total):
        self.items    = items
        self.page     = page
        self.per_page = per_page
        self.total    = total
        self.pages    = max(1, (total + per_page - 1) // per_page)
        self.has_prev = page > 1
        self.has_next = page < self.pages
        self.prev_num = page - 1 if self.has_prev else None
        self.next_num = page + 1 if self.has_next else None
        self.first_item = (page - 1) * per_page + 1 if total > 0 else 0
        self.last_item  = min(page * per_page, total)

    def iter_pages(self, left_edge=2, left_current=2, right_current=3, right_edge=2):
        last = 0
        for num in range(1, self.pages + 1):
            if (num <= left_edge
                    or (self.page - left_current - 1 < num < self.page + right_current)
                    or num > self.pages - right_edge):
                if last + 1 != num:
                    yield None
                yield num
                last = num


def paginate(query):
    """Apply LIMIT/OFFSET pagination to *query* using ?page and ?per_page from the request.

    Reads ADMIN_PAGE_SIZE from the app config (default 20).
    Allowed per_page values: 10, 20, 50.
    Returns a :class:`PaginationResult`.
    """
    from flask import request, current_app
    cfg_size = current_app.config.get('ADMIN_PAGE_SIZE', 20)
    try:
        per_page = int(request.args.get('per_page', cfg_size))
    except (TypeError, ValueError):
        per_page = cfg_size
    if per_page not in _ALLOWED_PAGE_SIZES:
        per_page = cfg_size
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (TypeError, ValueError):
        page = 1
    total = query.count()
    items = query.limit(per_page).offset((page - 1) * per_page).all()
    return PaginationResult(items, page, per_page, total)


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
