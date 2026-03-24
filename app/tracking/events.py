"""Named user-event tracking and booking funnel step recording."""
import json
import logging
from datetime import datetime, timezone

_log = logging.getLogger('tracking')

FUNNEL_STEP_ORDER = {
    'experience_view':   1,
    'booking_start':     2,
    'timeslot_select':   3,
    'cart_add':          4,
    'checkout_start':    5,
    'payment_attempt':   6,
    'booking_complete':  7,
}


def track_event(event_type: str, category: str,
                target_id: str = None, target_type: str = None,
                metadata: dict = None):
    """
    Record a named user event. Safe to call from any route.
    Silently catches all exceptions — tracking must never break the app.
    """
    try:
        from flask import request, g
        from flask_login import current_user
        from app.models import UserEvent
        from app.extensions import db
        from app.utils import generate_pk

        session_id = None
        site_sess  = getattr(g, 'site_session', None)
        if site_sess:
            session_id = site_sess.session_id

        event = UserEvent(
            event_id       = generate_pk(),
            session_id     = session_id,
            user_id        = current_user.user_id if current_user.is_authenticated else None,
            event_type     = event_type,
            event_category = category,
            url_path       = request.path[:500],
            target_id      = target_id,
            target_type    = target_type,
            event_meta     = json.dumps(metadata) if metadata else None,
            occurred_at    = datetime.now(timezone.utc),
        )
        db.session.add(event)
        db.session.commit()
    except Exception as exc:
        _log.error(f'track_event({event_type}) failed: {exc}')


def track_funnel_step(step_name: str, experience_id: str = None):
    """Record a booking funnel step for the current session."""
    try:
        from flask import g
        from app.models import FunnelStep
        from app.extensions import db
        from app.utils import generate_pk
        from datetime import datetime, timezone

        site_sess  = getattr(g, 'site_session', None)
        session_id = site_sess.session_id if site_sess else None

        step = FunnelStep(
            step_id       = generate_pk(),
            session_id    = session_id,
            experience_id = experience_id,
            step_name     = step_name,
            step_order    = FUNNEL_STEP_ORDER.get(step_name, 0),
            entered_at    = datetime.now(timezone.utc),
        )
        db.session.add(step)
        db.session.commit()
    except Exception as exc:
        _log.error(f'track_funnel_step({step_name}) failed: {exc}')
