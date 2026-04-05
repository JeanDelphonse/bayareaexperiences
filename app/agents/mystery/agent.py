"""Mystery Tour Agent — BAE-AGENT-MYSTERY (fully autonomous)"""
import json
import logging
import os
from datetime import datetime, timezone

from app.agents.base import BaseAgent

log = logging.getLogger('agents')

MYSTERY_SYSTEM_PROMPT = """
You are the experience designer for Bay Area Experiences.
Your job is to design a complete surprise day itinerary
for a customer who booked 'The Bay Area Surprise.'
They chose a vibe but know nothing else about the day.

RULES:
- Select from REAL Bay Area locations and experiences only.
- The day must start from the customer's pickup city.
- 4-6 stops total. Each stop must be distinct.
- Prioritize local events happening on the tour date.
- Match every stop to the customer's vibe:
  Adventure: coastal trails, headlands, active viewpoints
  Foodie: markets, wineries, food halls, farm stops
  Culture: murals, galleries, historic districts, music
  Relax: scenic drives, waterfront, low-activity stops
  Celebrate: photo-worthy spots, winery, waterfront
- Drive times must be realistic for Bay Area.
- Write the reveal email in first person from Jean.
- Output ONLY valid JSON.
"""


class MysteryTourAgent(BaseAgent):
    code        = 'BAE-AGENT-MYSTERY'
    max_tokens  = 2000
    temperature = 0.9

    def execute(self, context: dict, run) -> dict:
        booking_id   = context.get('booking_id')
        customer     = context.get('customer_name', 'Guest')
        pickup_city  = context.get('pickup_city', 'San Francisco')
        tour_date    = context.get('tour_date', '')
        vibe         = context.get('vibe', 'adventure')
        guest_count  = context.get('guest_count', 2)
        accessibility= context.get('accessibility', 'None noted')
        dietary      = context.get('dietary', 'None noted')
        local_events = context.get('local_events', 'No specific events found')
        weather      = context.get('weather', 'Mild Bay Area weather expected')

        user_prompt = f"""
Design a surprise Bay Area day for this booking:

CUSTOMER: {customer}
PICKUP CITY: {pickup_city}
TOUR DATE: {tour_date}
VIBE: {vibe}
GUEST COUNT: {guest_count}
ACCESSIBILITY NOTES: {accessibility}
DIETARY NOTES: {dietary}

LOCAL EVENTS on {tour_date} near {pickup_city}:
{local_events}

WEATHER on {tour_date} in {pickup_city}: {weather}

Return JSON:
{{
  "itinerary_title": "A catchy 5-word title for the day",
  "reveal_email_subject": "subject line for the morning reveal email",
  "reveal_email_body": "warm personal reveal email from Jean",
  "pickup": {{"address": "...", "time": "HH:MM AM/PM", "note": "..."}},
  "stops": [
    {{
      "order": 1, "name": "...", "arrival_time": "...",
      "duration_minutes": 60,
      "description": "why this stop fits the vibe",
      "surprise_reveal": "what the customer will say when they see it",
      "drive_from_prev": "..."
    }}
  ],
  "return": {{"estimated_time": "...", "drop_off": "..."}},
  "staff_notes": "guide preparation notes — keep the surprise until arrival"
}}
"""
        raw = self.claude(MYSTERY_SYSTEM_PROMPT, user_prompt)
        result = json.loads(raw)
        result['booking_id'] = booking_id
        return result

    def requires_approval(self, output: dict) -> bool:
        return False  # Fully autonomous

    def publish(self, output: dict, run):
        """Send the reveal email to the customer and update booking."""
        booking_id = output.get('booking_id')
        if not booking_id:
            return

        from app.models import Booking
        from app.extensions import db, mail as _mail
        from app.utils import send_email

        booking = Booking.query.get(booking_id)
        if not booking:
            return

        try:
            send_email(
                _mail,
                subject    = output.get('reveal_email_subject', 'Your Bay Area Surprise is here!'),
                recipients = [booking.guest_email],
                body_html  = f'<div style="font-family:sans-serif;max-width:600px;margin:auto">'
                             f'{output.get("reveal_email_body", "").replace(chr(10), "<br>")}</div>',
                body_text  = output.get('reveal_email_body', ''),
            )
            booking.mystery_reveal_sent_at = datetime.now(timezone.utc)
            db.session.commit()
            log.info(f'[MYSTERY] Reveal email sent for booking {booking_id}')
        except Exception as e:
            log.error(f'[MYSTERY] Reveal send failed for {booking_id}: {e}')


def schedule_mystery_reveals():
    """
    Called by a daily cron job at MYSTERY_REVEAL_HOUR (default 7 AM).
    Finds all mystery bookings for today that haven't had their reveal sent.
    """
    from app.models import Booking, Experience
    from flask import current_app

    reveal_hour = int(os.environ.get('MYSTERY_REVEAL_HOUR', 7))
    now = datetime.now(timezone.utc)
    if now.hour != reveal_hour:
        return

    today_str = now.strftime('%Y-%m-%d')

    bookings = (Booking.query
                .join(Experience)
                .filter(
                    Experience.is_mystery      == True,
                    Booking.booking_status     == 'confirmed',
                    Booking.mystery_reveal_sent_at == None,
                )
                .all())

    for booking in bookings:
        if not booking.timeslot:
            continue
        if str(booking.timeslot.slot_date) != today_str:
            continue
        _trigger_mystery_reveal(booking)


def _trigger_mystery_reveal(booking):
    from app.itinerary.events import get_local_events
    from app.weather.client import fetch_forecast_for_date
    from app.weather.cities import SERVING_CITIES

    city_name = booking.pickup_city.replace(', CA', '').strip()

    # Local events
    try:
        events = get_local_events(city_name, 'CA', str(booking.timeslot.slot_date))
        events_str = '; '.join(e['name'] for e in events) if events else 'No specific events found'
    except Exception:
        events_str = 'No specific events found'

    # Weather
    try:
        city_data = next((c for c in SERVING_CITIES if c['name'] == city_name), None)
        weather_day = None
        if city_data:
            weather_day = fetch_forecast_for_date(
                city_data['lat'], city_data['lng'], str(booking.timeslot.slot_date))
        weather_str = (f"{weather_day['condition']}, {weather_day['high_f']}°F high"
                       if weather_day else 'Mild Bay Area weather expected')
    except Exception:
        weather_str = 'Mild Bay Area weather expected'

    agent = MysteryTourAgent()
    agent.run(
        trigger_type   = 'event',
        trigger_detail = f'booking_id={booking.booking_id}',
        context        = {
            'booking_id'   : booking.booking_id,
            'customer_name': booking.guest_first_name,
            'pickup_city'  : city_name,
            'tour_date'    : str(booking.timeslot.slot_date),
            'vibe'         : booking.mystery_vibe or 'adventure',
            'guest_count'  : booking.guest_count,
            'accessibility': booking.special_requests or 'None noted',
            'dietary'      : 'None noted',
            'local_events' : events_str,
            'weather'      : weather_str,
        },
    )
