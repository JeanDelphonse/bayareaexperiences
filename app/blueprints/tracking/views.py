from flask import request, jsonify, make_response
from app.blueprints.tracking import tracking_bp
from app.extensions import db


@tracking_bp.route('/tracking/beacon', methods=['POST'])
def beacon():
    """Time-on-page beacon — no auth required. Browser fire-and-forget."""
    data    = request.get_json(silent=True) or {}
    view_id = str(data.get('view_id', ''))[:9]
    seconds = data.get('time_on_page', 0)
    if view_id and isinstance(seconds, int) and 0 < seconds < 86400:
        try:
            from app.models import PageView
            PageView.query.filter_by(view_id=view_id).update(
                {'time_on_page_seconds': seconds})
            db.session.commit()
        except Exception:
            pass
    return '', 204


@tracking_bp.route('/tracking/consent', methods=['POST'])
def consent():
    """Accept or decline cookie/tracking consent."""
    data   = request.get_json(silent=True) or {}
    accept = bool(data.get('accept', False))

    resp = make_response(jsonify({'ok': True}))
    resp.set_cookie(
        'tracking_consent',
        '1' if accept else '0',
        max_age=365 * 24 * 3600,
        httponly=True,
        samesite='Lax',
    )

    try:
        from flask import session as flask_session
        from app.models import SiteSession
        session_id = flask_session.get('tracking_session_id')
        if session_id:
            site_sess = SiteSession.query.get(session_id)
            if site_sess:
                site_sess.consent_given = accept
                db.session.commit()
    except Exception:
        pass

    return resp
