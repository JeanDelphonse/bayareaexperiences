"""Pre-booking AI recommendation generator."""
import anthropic
import json
import logging
import os

log = logging.getLogger('preferences')

RECO_SYSTEM_PROMPT = """
You are an enthusiastic Bay Area local guide for Bay Area Experiences.
Your job is to generate 2-3 short, exciting preview recommendations for a
customer who has selected their traveler preferences before booking a tour.

RULES:
- Each recommendation is 1-2 sentences maximum.
- Be specific to the Bay Area — reference real places, neighborhoods, or facts.
- Reflect the customer's chosen personas directly.
- Mention 1 local event if one is relevant to their interests.
- Do NOT repeat what is already in the experience description.
- Tone: warm, personal, genuinely excited — like a friend who knows the city.
- Output ONLY valid JSON — no prose before or after.
"""

RECO_PROMPT_TEMPLATE = """
Generate preview recommendations for this booking:

EXPERIENCE: {experience_name}
PICKUP CITY: {pickup_city}
TOUR DATE: {tour_date}
TRAVELER PERSONAS: {personas}
INTEREST TAGS: {interest_tags}
LOCAL EVENTS NEAR {pickup_city} ON {tour_date}:
{local_events_text}

Return JSON:
{{
  "headline": "One line that captures the spirit of their day (max 12 words)",
  "recommendations": [
    {{"text": "1-2 sentence recommendation", "persona": "which persona this speaks to"}},
    {{"text": "1-2 sentence recommendation", "persona": "..."}},
    {{"text": "1-2 sentence recommendation", "persona": "..."}}
  ]
}}
"""


def generate_recommendations(experience, pickup_city: str, tour_date: str,
                              personas: list, interest_tags: list) -> dict:
    """
    Generate 2-3 personalized preview recommendations.
    Called after customer selects personas on the Preference Step page.
    Returns dict or empty fallback — never raises.
    """
    try:
        from app.itinerary.events import get_local_events, CITY_STATE
        state_code = CITY_STATE.get(pickup_city, 'CA')
        local_events = get_local_events(
            city=pickup_city,
            state_code=state_code,
            tour_date=tour_date,
            experience_slug=experience.slug,
        )
        events_text = '\n'.join([
            f'- {e["name"]} at {e["venue"]} ({e["category"]})'
            for e in local_events[:3]
        ]) if local_events else 'No major events found for this date.'

        prompt = RECO_PROMPT_TEMPLATE.format(
            experience_name   = experience.name,
            pickup_city       = pickup_city,
            tour_date         = tour_date,
            personas          = ', '.join(personas) if personas else 'No personas selected',
            interest_tags     = ', '.join(interest_tags) if interest_tags else 'None',
            local_events_text = events_text,
        )

        max_tokens  = int(os.environ.get('RECO_MAX_TOKENS', 512))
        temperature = float(os.environ.get('RECO_TEMPERATURE', 0.6))

        client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
        msg = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=max_tokens,
            temperature=temperature,
            system=RECO_SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith('```'):
            raw = raw.split('\n', 1)[1].rsplit('```', 1)[0]
        return json.loads(raw)

    except Exception as e:
        log.error(f'Recommendations failed: {e}')
        return {'headline': '', 'recommendations': []}
