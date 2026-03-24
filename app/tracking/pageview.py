"""Record a page view after each tracked request."""
import logging
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode

_log = logging.getLogger('tracking')

# Query params to preserve (strip everything else for privacy)
_SAFE_PARAMS = frozenset({
    'page', 'per_page', 'sort', 'from', 'to', 'filter', 'status',
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_content',
})


def _safe_query(qs_bytes) -> str:
    try:
        qs = qs_bytes.decode('utf-8', errors='replace') if isinstance(qs_bytes, bytes) else qs_bytes
        params = parse_qs(qs, keep_blank_values=False)
        safe   = {k: v for k, v in params.items() if k in _SAFE_PARAMS}
        return urlencode(safe, doseq=True)[:500]
    except Exception:
        return ''


def record_page_view(site_session, response, response_ms: int):
    """Create a PageView record. Called from after_request. Never raises."""
    try:
        from flask import request, g
        from app.models import PageView, SiteSession
        from app.extensions import db

        # Only store page_views if visitor has given consent
        consent = request.cookies.get('tracking_consent') == '1'
        if not consent:
            # Still count pages for bounce detection (no PII stored)
            site_session.page_count = (site_session.page_count or 0) + 1
            if site_session.page_count > 1:
                site_session.is_bounce = False
            db.session.commit()
            return

        view_id = getattr(g, 'current_view_id', None)
        if not view_id:
            from app.utils import generate_pk
            view_id = generate_pk()

        view = PageView(
            view_id          = view_id,
            session_id       = site_session.session_id,
            user_id          = site_session.user_id,
            url_path         = request.path[:500],
            url_query        = _safe_query(request.query_string),
            http_method      = request.method[:4],
            http_status      = response.status_code,
            response_time_ms = response_ms,
            viewed_at        = datetime.now(timezone.utc),
        )
        db.session.add(view)

        # Increment page count; clear bounce flag after second page
        site_session.page_count = (site_session.page_count or 0) + 1
        if site_session.page_count > 1:
            site_session.is_bounce = False

        db.session.commit()

    except Exception as exc:
        _log.error(f'record_page_view failed: {exc}')
