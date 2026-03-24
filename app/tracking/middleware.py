"""Flask before/after_request tracking middleware.
Registered once in create_app() via init_tracking(app).
"""
import time
import os

EXCLUDED_PREFIXES = (
    '/admin',
    '/static',
    '/chat/',
    '/tracking/',
    '/favicon',
    '/robots.txt',
    '/sitemap.xml',
    '/book/timeslot',   # JSON API — not a page view
    '/checkout/create-payment-intent',
)


def init_tracking(app):
    """Register page-view tracking hooks on the Flask app."""

    @app.before_request
    def tracking_before():
        from flask import request, g
        from app.utils import generate_pk

        if not app.config.get('TRACKING_ENABLED', True):
            return
        if any(request.path.startswith(p) for p in EXCLUDED_PREFIXES):
            return

        g.request_start   = time.monotonic()
        g.current_view_id = generate_pk()   # Pre-generated so template can embed it

        try:
            from app.tracking.session import get_or_create_session
            g.site_session = get_or_create_session()
        except Exception:
            g.site_session = None

    @app.after_request
    def tracking_after(response):
        from flask import g, request

        if not app.config.get('TRACKING_ENABLED', True):
            return response
        if not hasattr(g, 'site_session') or g.site_session is None:
            return response
        if any(request.path.startswith(p) for p in EXCLUDED_PREFIXES):
            return response

        try:
            response_ms = int((time.monotonic() - g.request_start) * 1000)
            from app.tracking.pageview import record_page_view
            record_page_view(g.site_session, response, response_ms)
        except Exception:
            pass

        return response
