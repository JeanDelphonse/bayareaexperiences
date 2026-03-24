"""Visitor session management — get or create a SiteSession record."""
import hashlib
from datetime import datetime, timezone, timedelta
from flask import request, session as flask_session, g
from flask_login import current_user

SESSION_TIMEOUT_MINUTES = 30


def anonymize_ip(ip: str) -> str:
    """Zero the last octet of IPv4; truncate IPv6."""
    if not ip:
        return '0.0.0.0'
    parts = ip.split('.')
    if len(parts) == 4:        # IPv4
        parts[-1] = '0'
        return '.'.join(parts)
    return ip.split(':')[0] + '::0'  # IPv6 simplification


def get_or_create_session():
    """Return the active SiteSession for the current request, creating one if needed."""
    from app.models import SiteSession
    from app.extensions import db
    from app.utils import generate_pk
    from app.tracking.device import parse_device
    from app.tracking.referrer import classify_referrer, parse_domain
    from app.tracking.geo import get_location

    session_id = flask_session.get('tracking_session_id')
    site_sess  = None

    if session_id:
        site_sess = SiteSession.query.get(session_id)
        if site_sess:
            timeout_threshold = datetime.now(timezone.utc) - timedelta(minutes=SESSION_TIMEOUT_MINUTES)
            if site_sess.last_seen_at < timeout_threshold:
                # Expire old session
                site_sess.ended_at = site_sess.last_seen_at
                site_sess.duration_seconds = int(
                    (site_sess.ended_at - site_sess.started_at).total_seconds())
                db.session.commit()
                site_sess = None

    if not site_sess:
        raw_ip   = request.remote_addr or '0.0.0.0'
        anon_ip  = anonymize_ip(raw_ip)
        ip_hash  = hashlib.sha256(anon_ip.encode()).hexdigest()
        ua_str   = request.user_agent.string or ''
        device   = parse_device(ua_str)
        referrer = request.referrer or ''
        ref_type = classify_referrer(referrer)
        ref_dom  = parse_domain(referrer)
        geo      = get_location(anon_ip)

        consent = request.cookies.get('tracking_consent') == '1'

        site_sess = SiteSession(
            session_id      = generate_pk(),
            user_id         = current_user.user_id if current_user.is_authenticated else None,
            ip_hash         = ip_hash if consent else None,
            user_agent      = ua_str[:500] if ua_str else None,
            device_type     = device['type'],
            browser         = device['browser'],
            os              = device['os'],
            referrer_url    = referrer[:1000] if referrer else None,
            referrer_domain = ref_dom,
            referrer_type   = ref_type,
            utm_source      = request.args.get('utm_source', '')[:200] or None,
            utm_medium      = request.args.get('utm_medium', '')[:200] or None,
            utm_campaign    = request.args.get('utm_campaign', '')[:200] or None,
            utm_content     = request.args.get('utm_content', '')[:200] or None,
            country         = geo.get('country'),
            region          = geo.get('region'),
            city            = geo.get('city'),
            consent_given   = consent,
        )
        db.session.add(site_sess)
        db.session.commit()
        flask_session['tracking_session_id'] = site_sess.session_id

    # Update last_seen_at on every request
    site_sess.last_seen_at = datetime.now(timezone.utc)
    db.session.commit()
    return site_sess
