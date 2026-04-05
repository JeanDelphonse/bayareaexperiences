"""Google Ads Agent — BAE-AGENT-ADS"""
import json
import logging

from app.agents.base import BaseAgent

log = logging.getLogger('agents')

COPY_SYSTEM_PROMPT = """
You write Google Search Ad copy for Bay Area Experiences,
a private tour company in the San Francisco Bay Area.

Google Ads constraints:
- Headline: max 30 characters each (3 headlines per ad)
- Description: max 90 characters each (2 descriptions per ad)
- Never use superlatives that cannot be verified
- Include the key differentiator: private, up to 4 guests, door-to-door

BAE differentiators to emphasize:
- Private — not a bus tour, not shared
- Door-to-door pickup from customer's location
- Up to 4 guests — intimate group
- Includes snacks and water
- Expert local guide

Output ONLY valid JSON.
"""


class GoogleAdsAgent(BaseAgent):
    code        = 'BAE-AGENT-ADS'
    temperature = 0.4
    max_tokens  = 1200

    def execute(self, context: dict, run) -> dict:
        from app.models import AgentAdCopy
        from app.extensions import db
        from app.utils import generate_pk

        ad_group   = context.get('ad_group', 'General Bay Area Tours')
        keywords   = context.get('keywords', ['private tour San Francisco'])
        top_kw     = context.get('top_keyword', 'private tour San Francisco')
        perf_notes = context.get('performance_notes', 'No performance data yet.')

        user_prompt = f"""
Generate 3 Google Search Ad variants for this ad group:

AD GROUP: {ad_group}
TARGET KEYWORD: {top_kw}
RELATED KEYWORDS: {', '.join(keywords[:5])}
PERFORMANCE NOTES: {perf_notes}

Return JSON:
{{
  "ad_group": "{ad_group}",
  "variants": [
    {{
      "headlines": ["max 30 chars", "max 30 chars", "max 30 chars"],
      "descriptions": ["max 90 chars", "max 90 chars"],
      "angle": "what differentiator this variant emphasizes"
    }}
  ],
  "suggested_keywords": ["new keyword ideas"],
  "suggested_negatives": ["terms to exclude"]
}}
"""
        raw = self.claude(COPY_SYSTEM_PROMPT, user_prompt)
        draft = json.loads(raw)

        saved_ids = []
        for i, variant in enumerate(draft.get('variants', []), 1):
            copy = AgentAdCopy(
                copy_id      = generate_pk(),
                run_id       = run.run_id,
                ad_group     = ad_group,
                variant_index= i,
                headlines    = json.dumps(variant.get('headlines', [])),
                descriptions = json.dumps(variant.get('descriptions', [])),
                angle        = variant.get('angle', ''),
                status       = 'draft',
            )
            db.session.add(copy)
            saved_ids.append({'index': i, 'copy_id': copy.copy_id})
        db.session.commit()
        draft['saved_copy_ids'] = saved_ids
        return draft

    def requires_approval(self, output: dict) -> bool:
        return True

    def publish(self, output: dict, run):
        """Stub — real integration: Google Ads API."""
        from app.models import AgentAdCopy
        from app.extensions import db
        for item in output.get('saved_copy_ids', []):
            copy = AgentAdCopy.query.get(item['copy_id'])
            if copy:
                copy.status = 'live'
                copy.google_ad_id = 'pending-api-integration'
        db.session.commit()
        log.info(f'[ADS] Pushed ad copies to Google Ads (API integration pending)')
