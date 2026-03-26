"""Claude AI itinerary generator."""
import json
import logging
import os
from datetime import datetime, timezone

import anthropic

from app.itinerary.events import get_local_events, CITY_STATE

log = logging.getLogger('itinerary')

SYSTEM_PROMPT = """
You are an expert Bay Area tour planner for Bay Area Experiences.
Your task is to generate a personalized, well-structured day itinerary
for a customer who has booked a specific tour experience.

RULES:
- The itinerary MUST start from the customer's pickup city.
- The core stops must match exactly what is promised in the experience
  title and description. Do not invent new stops.
- You may mention 1-2 local events happening near the pickup city on the
  tour date as context/color - label them as optional 'Local Buzz' items.
  Do NOT route the tour through the event venue unless it is directly on
  the tour route. These are conversation pieces, not mandatory stops.
- Drive times must be reasonable and realistic for Bay Area traffic.
  San Jose to SF = 45-60 min depending on time of day.
  Santa Cruz to SF = 70-90 min.
  Monterey to SF = 100-120 min.
- All times are suggestions - the guide has discretion on the day.
- Keep language warm, conversational, and specific to the Bay Area.
- Output ONLY valid JSON - no prose before or after the JSON object.
"""

USER_PROMPT_TEMPLATE = """
Generate a day itinerary for this booking:

EXPERIENCE:
  Name: {experience_name}
  Description: {experience_description}
  Duration: {duration_hours} hours
  Core stops/highlights: {core_stops}
  Inclusions: Door-to-door pickup, complimentary snacks and water on board

BOOKING DETAILS:
  Customer: {customer_name}
  Guest Count: {guest_count}
  Pickup City: {pickup_city}, CA
  Pickup Address: {pickup_address}
  Tour Date: {tour_date}
  Timeslot Start: {start_time}
  Special Requests: {special_requests}

LOCAL EVENTS near {pickup_city} on {tour_date}:
{local_events_text}

Return a JSON object with this exact structure:
{{
  "itinerary_title": "string",
  "greeting": "2-3 sentence warm welcome personalized to the customer",
  "pickup": {{
    "address": "string",
    "time": "HH:MM AM/PM",
    "note": "brief note for customer about the pickup"
  }},
  "local_buzz": [
    {{
      "title": "event name",
      "description": "1-2 sentences about this event and why it is interesting context for the day",
      "venue": "venue name",
      "url": "event URL if available"
    }}
  ],
  "stops": [
    {{
      "order": 1,
      "name": "stop name",
      "arrival_time": "HH:MM AM/PM",
      "duration_minutes": 45,
      "description": "what the customer will see/do here",
      "highlight": "the single most memorable thing about this stop",
      "drive_from_prev": "e.g. 25-min drive from San Jose along 101"
    }}
  ],
  "return": {{
    "estimated_time": "HH:MM AM/PM",
    "drop_off": "same address as pickup unless otherwise noted"
  }},
  "inclusions": ["list", "of", "what", "is", "included"],
  "staff_notes": "1-2 sentence note specifically for the guide about pickup logistics or anything unusual about this booking",
  "generated_at": "ISO timestamp"
}}
"""


def generate_itinerary(booking) -> dict:
    """
    Generate a personalized itinerary for a booking.
    Returns the itinerary as a Python dict.
    Never raises - returns a fallback dict on any failure.
    """
    try:
        experience  = booking.experience
        timeslot    = booking.timeslot
        tour_date   = str(timeslot.slot_date)
        start_time  = timeslot.start_time.strftime('%I:%M %p') if timeslot.start_time else '9:00 AM'
        pickup_city = booking.pickup_city or 'San Francisco'
        state_code  = CITY_STATE.get(pickup_city, 'CA')

        local_events = get_local_events(
            city=pickup_city,
            state_code=state_code,
            tour_date=tour_date,
            experience_slug=experience.slug,
        )

        if local_events:
            local_events_text = '\n'.join([
                f'- {ev["name"]} at {ev["venue"]} ({ev["category"]}) - {ev["url"]}'
                for ev in local_events[:3]
            ])
        else:
            local_events_text = 'No major events found for this date - the city will be relaxed.'

        if booking.user:
            customer_name = f'{booking.user.first_name} {booking.user.last_name}'
        else:
            customer_name = f'{booking.guest_first_name} {booking.guest_last_name}'

        prompt = USER_PROMPT_TEMPLATE.format(
            experience_name=experience.name,
            experience_description=experience.description or '',
            duration_hours=experience.duration_hours,
            core_stops=experience.core_stops or 'As described in the experience',
            customer_name=customer_name,
            guest_count=booking.guest_count or 1,
            pickup_city=pickup_city,
            pickup_address=booking.pickup_address or f'{pickup_city}, CA',
            tour_date=tour_date,
            start_time=start_time,
            special_requests=booking.special_requests or 'None',
            local_events_text=local_events_text,
        )

        enabled = os.environ.get('ITINERARY_ENABLED', 'True').lower() != 'false'
        if not enabled:
            return _fallback_itinerary(booking)

        max_tokens  = int(os.environ.get('ITINERARY_CLAUDE_MAX_TOKENS', 2048))
        temperature = float(os.environ.get('ITINERARY_CLAUDE_TEMPERATURE', 0.4))

        client  = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
        message = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=max_tokens,
            temperature=temperature,
            system=SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': prompt}],
        )

        raw = message.content[0].text.strip()
        if raw.startswith('```'):
            raw = raw.split('\n', 1)[1].rsplit('```', 1)[0]

        itinerary = json.loads(raw)
        itinerary['generated_at']    = datetime.now(timezone.utc).isoformat()
        itinerary['booking_id']       = booking.booking_id
        itinerary['version']          = 1
        itinerary['local_events_raw'] = local_events

        return itinerary

    except Exception as e:
        log.error(f'Itinerary generation failed for {booking.booking_id}: {e}')
        return _fallback_itinerary(booking)


def _fallback_itinerary(booking) -> dict:
    return {
        'itinerary_title': booking.experience.name,
        'greeting': f'We look forward to welcoming you on {booking.timeslot.slot_date}.',
        'pickup': {
            'address': booking.pickup_address or booking.pickup_city,
            'time': booking.timeslot.start_time.strftime('%I:%M %p') if booking.timeslot.start_time else '9:00 AM',
            'note': 'Your guide will be in touch to confirm pickup details.',
        },
        'local_buzz': [],
        'stops': [],
        'return': {
            'estimated_time': 'As per booking duration',
            'drop_off': booking.pickup_address or booking.pickup_city,
        },
        'inclusions': ['Door-to-door pickup', 'Snacks and water on board'],
        'staff_notes': 'Standard pickup - no special requests.',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'booking_id': booking.booking_id,
        'version': 0,
        'is_fallback': True,
        'local_events_raw': [],
    }
