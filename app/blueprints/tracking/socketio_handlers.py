from flask_socketio import emit, join_room, leave_room
from app.extensions import db, socketio
from app.utils import generate_pk
from datetime import datetime, timezone


@socketio.on('join_session', namespace='/tracking')
def on_join_session(data):
    """Staff driver or customer viewer joins a tracking room."""
    session_id = data.get('session_id', '')
    role       = data.get('role', 'viewer')
    if not session_id:
        return
    room = f'tracking_{session_id}'
    join_room(room)
    emit('joined', {'room': room, 'role': role})


@socketio.on('location_update', namespace='/tracking')
def on_location_update(data):
    """
    Receive GPS update from staff driver.
    Upserts tracking_locations (one row per session — always overwritten).
    Broadcasts latest position to all viewers in the session room.
    """
    from app.models import TrackingSession, TrackingLocation

    session_id = data.get('session_id', '')
    booking_id = data.get('booking_id', '')
    lat        = data.get('lat')
    lng        = data.get('lng')

    if not session_id or lat is None or lng is None:
        return

    now = datetime.now(timezone.utc)

    gps_session = TrackingSession.query.filter_by(
        session_id=session_id, status='active').first()
    if not gps_session:
        return

    gps_session.last_lat             = lat
    gps_session.last_lng             = lng
    gps_session.last_accuracy_meters = data.get('accuracy_meters')
    gps_session.last_updated_at      = now
    gps_session.update_count        += 1

    location = TrackingLocation.query.filter_by(session_id=session_id).first()
    if location:
        location.lat               = lat
        location.lng               = lng
        location.accuracy_meters   = data.get('accuracy_meters')
        location.heading           = data.get('heading')
        location.speed_kmh         = data.get('speed_kmh')
        location.recorded_at       = data.get('recorded_at', now.isoformat())
        location.server_received_at = now
    else:
        location = TrackingLocation(
            location_id         = generate_pk(),
            session_id          = session_id,
            booking_id          = booking_id,
            lat                 = lat,
            lng                 = lng,
            accuracy_meters     = data.get('accuracy_meters'),
            heading             = data.get('heading'),
            speed_kmh           = data.get('speed_kmh'),
            recorded_at         = data.get('recorded_at', now.isoformat()),
            server_received_at  = now,
        )
        db.session.add(location)

    db.session.commit()

    room = f'tracking_{session_id}'
    emit('driver_location', {
        'lat':        lat,
        'lng':        lng,
        'accuracy':   data.get('accuracy_meters'),
        'heading':    data.get('heading'),
        'speed_kmh':  data.get('speed_kmh'),
        'updated_at': now.isoformat(),
    }, room=room, namespace='/tracking')


@socketio.on('end_session', namespace='/tracking')
def on_end_session(data):
    from app.models import TrackingSession

    session_id = data.get('session_id', '')
    gps_session = TrackingSession.query.filter_by(session_id=session_id).first()
    if gps_session:
        gps_session.status   = 'ended'
        gps_session.ended_at = datetime.now(timezone.utc)
        db.session.commit()

    room = f'tracking_{session_id}'
    emit('tracking_ended', {}, room=room, namespace='/tracking')
    leave_room(room)
