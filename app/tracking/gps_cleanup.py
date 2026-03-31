"""
GPS tracking cleanup jobs.

Run via cPanel cron:
  */15 * * * *  cd /path/to/app && python -c "
      import sys; sys.path.insert(0,'.');
      from app import create_app
      from app.tracking.gps_cleanup import auto_terminate_sessions
      app = create_app('production')
      with app.app_context(): auto_terminate_sessions()"

  0 4 * * *  cd /path/to/app && python -c "
      import sys; sys.path.insert(0,'.');
      from app import create_app
      from app.tracking.gps_cleanup import purge_expired_location_data
      app = create_app('production')
      with app.app_context(): purge_expired_location_data()"
"""
from datetime import datetime, timezone, timedelta
from app.models import TrackingSession, TrackingLocation, BookingTrackingToken
from app.extensions import db, socketio


def auto_terminate_sessions():
    """
    Called every 15 minutes. Terminates active sessions that have exceeded
    their bounds (tour ended, idle too long, or running > 14 hours).
    """
    now    = datetime.now(timezone.utc)
    active = TrackingSession.query.filter_by(status='active').all()

    for session in active:
        booking  = session.booking
        timeslot = booking.timeslot

        try:
            end_dt = datetime.combine(
                timeslot.slot_date, timeslot.end_time, tzinfo=timezone.utc)
        except Exception:
            continue

        reason = None

        if now > end_dt + timedelta(minutes=30):
            reason = 'booking_end_passed'

        if not reason and session.last_updated_at:
            idle_min = (now - session.last_updated_at).total_seconds() / 60
            if idle_min > 30:
                reason = 'timeout_30min_no_signal'

        if not reason:
            running_hours = (now - session.started_at).total_seconds() / 3600
            if running_hours > 14:
                reason = 'max_duration_exceeded'

        if reason:
            session.status          = 'expired'
            session.ended_at        = now
            session.auto_end_reason = reason

            token = BookingTrackingToken.query.filter_by(
                booking_id=booking.booking_id).first()
            if token:
                token.is_active = False

            try:
                if socketio is not None:
                    socketio.emit('tracking_ended', {},
                                  room=f'tracking_{session.session_id}',
                                  namespace='/tracking')
            except Exception:
                pass

    db.session.commit()


def purge_expired_location_data():
    """
    Called nightly. Deletes TrackingLocation rows and clears last_lat/last_lng
    for sessions that ended more than GPS_DATA_PURGE_HOURS ago (default 2h).
    """
    from flask import current_app
    purge_hours = current_app.config.get('GPS_DATA_PURGE_HOURS', 2)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=purge_hours)

    expired = TrackingSession.query.filter(
        TrackingSession.status.in_(['ended', 'expired']),
        TrackingSession.ended_at <= cutoff,
    ).all()

    for session in expired:
        TrackingLocation.query.filter_by(session_id=session.session_id).delete()
        session.last_lat             = None
        session.last_lng             = None
        session.last_accuracy_meters = None

    db.session.commit()
