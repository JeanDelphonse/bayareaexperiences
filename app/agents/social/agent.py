"""Social Media Agent — BAE-AGENT-SOCIAL"""
import json
import logging
import os
from datetime import date

from app.agents.base import BaseAgent

log = logging.getLogger('agents')

SYSTEM_PROMPT = """
You are the social media voice for Bay Area Experiences,
a private tour company in the San Francisco Bay Area.
You write content for Instagram, TikTok, and LinkedIn.

BRAND VOICE:
- Warm, knowledgeable, never salesy
- Specific to the Bay Area — real places, real details
- Intimate — we take up to 4 guests. We are not a bus tour.
- Never use: 'unforgettable', 'world-class', 'once in a lifetime'

CONTENT ANGLES (rotate variety):
1. Experience spotlight — what you see/do on one specific tour
2. Price reframe — '$706 / 4 people = $176.50 per person' style
3. Staff POV — a moment from the guide's perspective
4. Local knowledge — something most visitors never find
5. Seasonal/event — tie to what's happening in the Bay this week
6. Behind the scenes — the Jeep, the snacks, the prep

OUTPUT FORMAT: Valid JSON only. No prose outside the JSON.
"""

USER_PROMPT = """
Generate a social media post for Bay Area Experiences.

TODAY'S CONTEXT:
  Date: {date}
  Day: {day_of_week}
  Season: {season}
  Recent bookings: {recent_experiences}
  Local events this week: {local_events}
  Last post angle used: {last_angle}
  Weather in SF this week: {sf_weather}

PLATFORM: {platform}

Return JSON:
{{
  "platform": "{platform}",
  "angle": "which content angle you used",
  "caption": "the full post caption",
  "hashtags": ["list", "of", "hashtags"],
  "call_to_action": "the CTA at end of caption",
  "best_post_time": "HH:MM in America/Los_Angeles",
  "notes_for_admin": "anything admin should know before approving"
}}
"""

SEASON_MAP = {12: 'Winter', 1: 'Winter', 2: 'Winter',
              3: 'Spring',  4: 'Spring',  5: 'Spring',
              6: 'Summer',  7: 'Summer',  8: 'Summer',
              9: 'Fall',   10: 'Fall',   11: 'Fall'}


class SocialMediaAgent(BaseAgent):
    code        = 'BAE-AGENT-SOCIAL'
    max_tokens  = 800
    temperature = 0.8

    def execute(self, context: dict, run) -> dict:
        from app.models import Booking, Experience, AgentSocialPost
        from app.extensions import db
        from app.utils import generate_pk

        today = date.today()
        season = SEASON_MAP[today.month]

        # Determine which platforms are enabled
        platforms = []
        for p in ('instagram', 'tiktok', 'linkedin'):
            if self.get_setting(f'{p}_enabled', True):
                platforms.append(p)
        if not platforms:
            platforms = ['instagram']

        platform = context.get('platform', platforms[0])

        # Recent confirmed experiences
        recent = (Booking.query
                  .join(Experience)
                  .filter(Booking.booking_status == 'confirmed')
                  .order_by(Booking.created_at.desc())
                  .limit(5).all())
        recent_exp = ', '.join({b.experience.name for b in recent}) or 'Bay Area tours'

        # Last angle used
        last_post = AgentSocialPost.query.order_by(AgentSocialPost.post_id.desc()).first()
        last_angle = last_post.angle if last_post else 'none'

        # SF weather summary
        sf_weather = context.get('sf_weather', 'mild Bay Area weather')

        # Local events
        local_events = context.get('local_events', 'no specific events this week')

        user_prompt = USER_PROMPT.format(
            date=today.isoformat(),
            day_of_week=today.strftime('%A'),
            season=season,
            recent_experiences=recent_exp,
            local_events=local_events,
            last_angle=last_angle,
            sf_weather=sf_weather,
            platform=platform,
        )

        raw = self.claude(SYSTEM_PROMPT, user_prompt)
        draft = json.loads(raw)

        # Persist the draft post record
        post = AgentSocialPost(
            post_id  = generate_pk(),
            run_id   = run.run_id,
            platform = draft.get('platform', platform),
            angle    = draft.get('angle', ''),
            caption  = draft.get('caption', ''),
            hashtags = json.dumps(draft.get('hashtags', [])),
            call_to_action = draft.get('call_to_action', ''),
            status   = 'draft',
        )
        db.session.add(post)
        db.session.commit()
        draft['post_id'] = post.post_id
        return draft

    def requires_approval(self, output: dict) -> bool:
        return True

    def publish(self, output: dict, run):
        """Stub — real integration: Meta Graph API / TikTok / LinkedIn API."""
        from app.models import AgentSocialPost
        from app.extensions import db
        post_id = output.get('post_id')
        if post_id:
            post = AgentSocialPost.query.get(post_id)
            if post:
                post.status = 'published'
                post.platform_post_id = 'pending-api-integration'
                db.session.commit()
        log.info(f'[SOCIAL] Published to {output.get("platform")} (API integration pending)')
