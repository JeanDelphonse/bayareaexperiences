"""Provider-specific access decorators."""
from functools import wraps
from flask import abort
from flask_login import current_user


def current_provider():
    """Return the Provider record for current_user, or None."""
    if not current_user.is_authenticated:
        return None
    return current_user.provider


def provider_required(f):
    """Require an active, approved provider account."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            from flask import redirect, url_for
            return redirect(url_for('auth.login'))
        p = current_user.provider
        if not p or not p.is_active:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def provider_active_required(f):
    """Require provider to be active AND approved to list experiences."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            from flask import redirect, url_for
            return redirect(url_for('auth.login'))
        p = current_user.provider
        if not p or not p.is_active or not p.can_list_experiences:
            abort(403)
        return f(*args, **kwargs)
    return decorated
