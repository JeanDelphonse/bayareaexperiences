"""
Sample itinerary generation — BAE-PRD-SAMPLE-ITINERARY-v1.0

Generated once per experience by Claude, cached in experiences.sample_itinerary.
No API call is made on subsequent page loads.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from types import SimpleNamespace

import anthropic

log = logging.getLogger('sample_itinerary')

SAMPLE_SYSTEM = """
You are the experience writer for Bay Area Experiences,
a private tour company in the San Francisco Bay Area.
Your job is to write a sample itinerary for an experience
detail page — marketing content that shows prospective
customers what a typical day looks like.

RULES:
- Use REAL Bay Area locations. No invented place names.
- Be specific: real road names, real viewpoints, real wineries.
- Write in second person ('You arrive at...', 'Your guide...')
- Tone: warm, knowledgeable, slightly literary — not corporate.
- Do NOT mention specific dates, local events, or weather.
  Those appear in the personalised booking itinerary.
- Do NOT mention specific pickup cities.
  Use 'We pick you up at your door in the Bay Area.'
- Each stop: 2-3 sentences description + 1 highlight sentence.
- Number of stops: match the experience duration
  (5hr = 3-4 stops, 8hr = 5-6 stops, 10hr = 6-7 stops).
- End with a warm return note.
- Include a disclaimer that this is a sample.
- Output ONLY valid JSON. No prose outside the JSON.
"""


def generate_sample_itinerary(experience) -> dict | None:
    """
    Call Claude to generate a sample itinerary for an experience.
    Returns the parsed dict or None on any failure — never raises.
    """
    user_prompt = f"""
Generate a sample itinerary for this Bay Area Experiences tour:

EXPERIENCE NAME: {experience.name}
CATEGORY:        {experience.category}
DURATION:        {experience.duration_hours} hours
DESCRIPTION:     {experience.description}
CORE STOPS:      {experience.core_stops or 'Not specified — use your knowledge of the Bay Area'}

Return a JSON object with this exact structure:
{{
  "title":       "A Day in [experience name]",
  "intro":       "2-sentence intro describing the experience arc",
  "duration":    "{experience.duration_hours} hours",
  "pickup_note": "short door-to-door pickup note",
  "stops": [
    {{
      "order":       1,
      "time":        "HH:MM AM/PM",
      "name":        "Stop name",
      "duration":    "XX min",
      "description": "2-3 sentences",
      "highlight":   "one memorable detail"
    }}
  ],
  "return_note": "warm closing note about return time",
  "disclaimer":  "This is a sample itinerary. Your actual itinerary is personalised to your group, pickup city, and tour date."
}}
"""
    try:
        client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
        msg = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=2000,
            temperature=0.6,
            system=SAMPLE_SYSTEM,
            messages=[{'role': 'user', 'content': user_prompt}],
        )
        raw = msg.content[0].text.strip()
        # Strip markdown fences if present
        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]
            raw = raw.strip()
        return json.loads(raw)
    except Exception as e:
        log.error('Sample itinerary generation failed for %s: %s',
                  experience.experience_id, e)
        return None


def store_sample_itinerary(experience_id: str, data: dict):
    """
    Persist the generated itinerary to experiences.sample_itinerary.
    Safe to call from a background thread — requires an active app context.
    """
    from app.extensions import db
    from app.models import Experience
    exp = Experience.query.get(experience_id)
    if exp and data:
        exp.sample_itinerary    = json.dumps(data)
        exp.sample_itinerary_at = datetime.now(timezone.utc)
        db.session.commit()


def generate_and_store_async(app, experience_id: str):
    """
    Fire-and-forget: generate in a background thread with its own app context.
    Used on the first detail page load when sample_itinerary is NULL.
    Zero visible latency for the visitor — skeleton shows while it runs.
    """
    def _run():
        with app.app_context():
            from app.extensions import db
            from app.models import Experience
            exp = Experience.query.get(experience_id)
            if not exp:
                return
            # Snapshot needed fields as plain values, then release the DB
            # connection before the Anthropic API call — prevents holding a
            # pool connection open for the full 2-4s generation time.
            snapshot = SimpleNamespace(
                experience_id  = exp.experience_id,
                name           = exp.name,
                category       = exp.category,
                duration_hours = exp.duration_hours,
                description    = exp.description,
                core_stops     = exp.core_stops,
            )
            db.session.remove()

            data = generate_sample_itinerary(snapshot)
            if data:
                store_sample_itinerary(experience_id, data)

    threading.Thread(target=_run, daemon=True).start()
