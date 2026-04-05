"""Partnership Agent — BAE-AGENT-PARTNER"""
import json
import logging
from datetime import datetime, timezone, timedelta

from app.agents.base import BaseAgent

log = logging.getLogger('agents')

OUTREACH_SYSTEM_PROMPT = """
You write personalized outreach emails for Bay Area Experiences,
a private small-group tour company in the San Francisco Bay Area.

You are reaching out to potential referral partners:
- Hotel concierges at boutique properties in the Bay Area
- Corporate HR managers and executive assistants at tech companies
- OTA (Viator, GetYourGuide) listing managers

BRAND VOICE:
- Professional but warm
- Lead with the value to their guests/employees, not BAE's revenue
- Be specific about the product (private, up to 4 guests, door-to-door)
- Keep the email under 200 words
- End with a clear, low-friction ask (a 15-minute call or a PDF)

Output ONLY valid JSON.
"""


class PartnershipAgent(BaseAgent):
    code        = 'BAE-AGENT-PARTNER'
    max_tokens  = 1000
    temperature = 0.6

    def execute(self, context: dict, run) -> dict:
        from app.models import Partner, PartnerOutreach
        from app.extensions import db
        from app.utils import generate_pk

        partner_id = context.get('partner_id')
        partner    = Partner.query.get(partner_id) if partner_id else None

        if not partner:
            # Find partners overdue for follow-up
            followup_days = int(self.get_setting('followup_days', 30))
            cutoff = datetime.now(timezone.utc) - timedelta(days=followup_days)
            partner = (Partner.query
                       .filter(Partner.status.in_(['prospect', 'contacted', 'active']),
                               (Partner.next_followup_at <= datetime.now(timezone.utc)) |
                               (Partner.last_contact_at <= cutoff) |
                               (Partner.last_contact_at == None))
                       .order_by(Partner.next_followup_at.asc())
                       .first())

        if not partner:
            return {'message': 'No partners due for outreach at this time.', 'skipped': True}

        user_prompt = f"""
Draft an outreach email for this partner:

PARTNER TYPE: {partner.partner_type}
BUSINESS NAME: {partner.business_name}
CONTACT NAME: {partner.contact_name or 'the team'}
LOCATION: {partner.location_city or 'Bay Area'}
CURRENT STATUS: {partner.status}
INTERNAL NOTES: {partner.notes or 'First contact'}

Return JSON:
{{
  "subject": "email subject line",
  "body": "full email body in plain text (under 200 words)",
  "outreach_type": "email",
  "notes_for_admin": "context on why this partner was selected"
}}
"""
        raw = self.claude(OUTREACH_SYSTEM_PROMPT, user_prompt)
        draft = json.loads(raw)

        outreach = PartnerOutreach(
            outreach_id   = generate_pk(),
            partner_id    = partner.partner_id,
            run_id        = run.run_id,
            outreach_type = draft.get('outreach_type', 'email'),
            subject       = draft.get('subject', ''),
            body          = draft.get('body', ''),
            status        = 'draft',
        )
        db.session.add(outreach)

        # Update next follow-up autonomously
        followup_days = int(self.get_setting('followup_days', 30))
        partner.next_followup_at = (datetime.now(timezone.utc) +
                                    timedelta(days=followup_days))
        db.session.commit()

        draft['outreach_id'] = outreach.outreach_id
        draft['partner_id']  = partner.partner_id
        draft['partner_name']= partner.business_name
        return draft

    def requires_approval(self, output: dict) -> bool:
        return not output.get('skipped', False)

    def publish(self, output: dict, run):
        """Send approved outreach email via Flask-Mail."""
        from app.models import Partner, PartnerOutreach
        from app.extensions import db, mail as _mail
        from app.utils import send_email

        outreach_id = output.get('outreach_id')
        partner_id  = output.get('partner_id')
        if not outreach_id:
            return

        outreach = PartnerOutreach.query.get(outreach_id)
        partner  = Partner.query.get(partner_id) if partner_id else None

        if outreach and partner and partner.contact_email:
            try:
                send_email(_mail,
                           subject    = outreach.subject,
                           recipients = [partner.contact_email],
                           body_html  = f'<pre style="font-family:sans-serif">{outreach.body}</pre>',
                           body_text  = outreach.body)
                now = datetime.now(timezone.utc)
                outreach.status    = 'sent'
                outreach.sent_at   = now
                partner.last_contact_at = now
                db.session.commit()
                log.info(f'[PARTNER] Outreach sent to {partner.business_name}')
            except Exception as e:
                log.error(f'[PARTNER] Send failed: {e}')
