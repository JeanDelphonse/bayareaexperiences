"""Email & Loyalty Agent — BAE-AGENT-EMAIL"""
import json
import logging

from app.agents.base import BaseAgent

log = logging.getLogger('agents')

SHARE_SYSTEM_PROMPT = """
You write a warm, personal post-tour email for Bay Area Experiences.
The email goes out 24 hours after a customer's tour.
Its purpose is to ask them to share their experience on social media
or leave a review — but it must feel like a genuine thank-you,
not a marketing request.

RULES:
- Address the customer by first name
- Reference the specific experience they took
- Reference their pickup city
- If they selected personas (History Buff, Foodie, etc.),
  reference what they cared about
- Keep it under 100 words
- One CTA only: share on social OR leave a review (not both)
- Sign off from Jean personally, not 'The BAE Team'
- Output ONLY valid JSON
"""

CAMPAIGN_SYSTEM_PROMPT = """
You write marketing campaign emails for Bay Area Experiences,
a private small-group tour company in the San Francisco Bay Area.

BRAND VOICE:
- Warm, personal, never spammy
- Specific to the Bay Area — real places, real details
- Focus on the experience, not the sale
- Subject lines under 50 characters, no clickbait

Output ONLY valid JSON.
"""


class EmailLoyaltyAgent(BaseAgent):
    code        = 'BAE-AGENT-EMAIL'
    max_tokens  = 1500
    temperature = 0.7

    def execute(self, context: dict, run) -> dict:
        """Generate a campaign email draft for admin approval."""
        from app.models import AgentEmailCampaign
        from app.extensions import db
        from app.utils import generate_pk

        campaign_type = context.get('campaign_type', 'weekly')
        segment       = context.get('segment', 'all_customers')
        angle         = context.get('angle', 'seasonal')

        user_prompt = f"""
Generate a campaign email for Bay Area Experiences.

CAMPAIGN TYPE: {campaign_type}
RECIPIENT SEGMENT: {segment}
ANGLE / HOOK: {angle}
CONTEXT: {json.dumps(context.get('extra', {}))}

Return JSON:
{{
  "subject_line": "email subject line (under 50 chars)",
  "preview_text": "email preview text (under 80 chars)",
  "body_html": "complete HTML email body",
  "body_text": "plain text version",
  "recommended_send_day": "e.g. Tuesday",
  "recommended_send_time": "HH:MM America/Los_Angeles",
  "notes_for_admin": "any notes about targeting or timing"
}}
"""
        raw = self.claude(CAMPAIGN_SYSTEM_PROMPT, user_prompt)
        draft = json.loads(raw)

        campaign = AgentEmailCampaign(
            campaign_id      = generate_pk(),
            run_id           = run.run_id,
            campaign_type    = campaign_type,
            subject_line     = draft.get('subject_line', ''),
            body_html        = draft.get('body_html', ''),
            body_text        = draft.get('body_text', ''),
            recipient_segment= segment,
            status           = 'draft',
        )
        db.session.add(campaign)
        db.session.commit()
        draft['campaign_id'] = campaign.campaign_id
        return draft

    def requires_approval(self, output: dict) -> bool:
        return True

    def publish(self, output: dict, run):
        """Send approved campaign via Flask-Mail."""
        from app.models import AgentEmailCampaign, User
        from app.extensions import db, mail as _mail
        from app.utils import send_email

        campaign_id = output.get('campaign_id')
        if not campaign_id:
            return
        campaign = AgentEmailCampaign.query.get(campaign_id)
        if not campaign:
            return

        # Build recipient list
        recipients = [u.email for u in User.query.filter_by(email_verified=True).all()]
        campaign.recipient_count = len(recipients)

        try:
            for email in recipients:
                send_email(_mail,
                           subject    = campaign.subject_line,
                           recipients = [email],
                           body_html  = campaign.body_html,
                           body_text  = campaign.body_text)
            from datetime import datetime, timezone
            campaign.sent_at = datetime.now(timezone.utc)
            campaign.status  = 'sent'
        except Exception as e:
            log.error(f'[EMAIL] Campaign send failed: {e}')
            campaign.status = 'cancelled'
        db.session.commit()


# ── Autonomous: post-tour share email ─────────────────────────────────────────

def generate_share_email(booking, preferences=None) -> dict:
    """
    Generate and send a personalized post-tour share/review request email.
    Called autonomously 24 hours after a booking's tour completes.
    """
    persona_note = ''
    if preferences and getattr(preferences, 'persona_labels', None):
        persona_note = f'They identified as: {preferences.persona_labels}'

    user_prompt = f"""
Generate a post-tour share email for:
  Customer: {booking.guest_first_name}
  Experience: {booking.experience.name}
  Pickup city: {booking.pickup_city}
  Tour date: {booking.timeslot.slot_date}
  {persona_note}
  Review link: https://bayareaexperiences.com/review/{booking.booking_id}
  Instagram: @bayareaexperiences

Return JSON:
{{
  "subject": "email subject line",
  "body_html": "full HTML email body",
  "body_text": "plain text version",
  "cta_type": "review or social"
}}
"""
    from app.agents.base import BaseAgent
    agent = BaseAgent()
    raw = agent.claude(SHARE_SYSTEM_PROMPT, user_prompt)
    result = json.loads(raw)

    # Send immediately (autonomous)
    try:
        from app.extensions import mail as _mail
        from app.utils import send_email
        send_email(_mail,
                   subject    = result['subject'],
                   recipients = [booking.guest_email],
                   body_html  = result['body_html'],
                   body_text  = result.get('body_text', ''))
        log.info(f'[EMAIL] Share email sent for booking {booking.booking_id}')
    except Exception as e:
        log.error(f'[EMAIL] Share email send failed for {booking.booking_id}: {e}')

    return result
