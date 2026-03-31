/**
 * staff_tracking.js — GPS broadcast for staff portal and briefing pages.
 *
 * Usage: include this script and set BOOKING_ID, GPS_UPDATE_INTERVAL_SECONDS,
 * and GPS_WINDOW_PRE_MINUTES as globals before loading this file.
 *
 * Required globals (set in the parent template):
 *   BOOKING_ID                 — 9-char booking PK
 *   GPS_UPDATE_INTERVAL_SECONDS — how often to emit (default 10)
 *   GPS_WINDOW_PRE_MINUTES      — how early staff can start (default 30)
 *   CSRF_TOKEN                  — Flask-WTF CSRF token string
 */

var _sessionId = null;
var _watchId   = null;
var _socket    = null;
var _wakeLock  = null;
var _lastSent  = 0;

/* ── Enable Start button only after consent ───────────────────────────── */
document.addEventListener('DOMContentLoaded', function () {
  var consentCheck = document.getElementById('consentCheck');
  var startBtn     = document.getElementById('startBtn');
  if (consentCheck && startBtn) {
    consentCheck.addEventListener('change', function () {
      startBtn.disabled     = !this.checked;
      startBtn.style.opacity = this.checked ? '1' : '0.45';
    });
  }
});

/* ── Start Tracking ───────────────────────────────────────────────────── */
async function startTracking() {
  var startBtn = document.getElementById('startBtn');
  if (startBtn) { startBtn.disabled = true; }

  var resp = await fetch('/tracking/start/' + BOOKING_ID, {
    method:  'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken':  typeof CSRF_TOKEN !== 'undefined' ? CSRF_TOKEN : '',
    },
    body: JSON.stringify({ consent: true }),
  });

  if (!resp.ok) {
    alert('Could not start tracking. Please try again.');
    if (startBtn) { startBtn.disabled = false; }
    return;
  }

  var data = await resp.json();
  _sessionId = data.session_id;

  /* Connect to SocketIO */
  _socket = io('/tracking', { transports: ['websocket', 'polling'] });
  _socket.on('connect', function () {
    _socket.emit('join_session', { session_id: _sessionId, role: 'driver' });
  });

  /* Start watching GPS */
  if (!navigator.geolocation) {
    alert('GPS is not available on this device.');
    return;
  }

  var intervalMs = (typeof GPS_UPDATE_INTERVAL_SECONDS !== 'undefined'
    ? GPS_UPDATE_INTERVAL_SECONDS : 10) * 1000;

  _watchId = navigator.geolocation.watchPosition(
    function (pos) {
      var now = Date.now();
      if (now - _lastSent < intervalMs - 500) { return; }   // throttle
      _lastSent = now;

      var loc = {
        session_id:      _sessionId,
        booking_id:      BOOKING_ID,
        lat:             pos.coords.latitude,
        lng:             pos.coords.longitude,
        accuracy_meters: pos.coords.accuracy,
        heading:         pos.coords.heading,
        speed_kmh:       pos.coords.speed ? pos.coords.speed * 3.6 : null,
        recorded_at:     new Date(pos.timestamp).toISOString(),
      };

      if (_socket) { _socket.emit('location_update', loc); }

      var statusEl = document.getElementById('trackStatus');
      if (statusEl) {
        statusEl.textContent =
          'GPS Active · Accuracy: ' + Math.round(pos.coords.accuracy) + 'm';
      }
    },
    function (err) {
      var statusEl = document.getElementById('trackStatus');
      if (statusEl) { statusEl.textContent = 'GPS error: ' + err.message; }
    },
    { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
  );

  /* Update UI */
  var trackStart  = document.getElementById('trackStart');
  var trackActive = document.getElementById('trackActive');
  if (trackStart)  { trackStart.style.display  = 'none'; }
  if (trackActive) { trackActive.style.display = 'block'; }

  _requestWakeLock();
}

/* ── Stop Tracking ────────────────────────────────────────────────────── */
async function stopTracking() {
  if (_watchId !== null) {
    navigator.geolocation.clearWatch(_watchId);
    _watchId = null;
  }
  if (_socket) {
    _socket.emit('end_session', { session_id: _sessionId });
    _socket.disconnect();
    _socket = null;
  }

  await fetch('/tracking/end/' + BOOKING_ID, {
    method:  'POST',
    headers: { 'X-CSRFToken': typeof CSRF_TOKEN !== 'undefined' ? CSRF_TOKEN : '' },
  });

  var trackActive = document.getElementById('trackActive');
  var trackEnded  = document.getElementById('trackEnded');
  if (trackActive) { trackActive.style.display = 'none'; }
  if (trackEnded)  { trackEnded.style.display  = 'block'; }

  _releaseWakeLock();
}

/* ── Screen Wake Lock ─────────────────────────────────────────────────── */
async function _requestWakeLock() {
  try {
    if ('wakeLock' in navigator) {
      _wakeLock = await navigator.wakeLock.request('screen');
    }
  } catch (e) { /* not supported — GPS still works */ }
}

function _releaseWakeLock() {
  if (_wakeLock) { _wakeLock.release(); _wakeLock = null; }
}

/* Re-acquire wake lock on visibility change (iOS workaround) */
document.addEventListener('visibilitychange', async function () {
  if (document.visibilityState === 'visible' && _watchId !== null) {
    await _requestWakeLock();
  }
});
