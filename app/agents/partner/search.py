"""Partner discovery agent — web search + CRM auto-import."""
import json
import logging
import os
import re
from datetime import datetime, timezone

log = logging.getLogger('agents')

_FENCE_RE = re.compile(r'```(?:json|JSON)?')

SEARCH_SYSTEM = """
You are a business research agent for Bay Area Experiences,
a private tour company in the San Francisco Bay Area.
Your job is to search the web for potential business partners
that match the admin's channel description.

For each business found, extract:
- business_name: official business name
- address: street address if available
- city: city name
- phone: phone number if available
- website: URL if available
- contact_name: specific contact person name if found
- contact_email: email address if found
- contact_title: job title if found (e.g. 'Concierge Manager')
- why_good_fit: 1 sentence on why this is a good BAE partner

RULES:
- Only include real, currently operating businesses.
- Do not include large chains (Hilton, Marriott, Sheraton, etc.).
- Prioritize businesses with a named contact or concierge desk.
- Output ONLY valid JSON — an array of business objects.
- If you cannot find enough results, return what you have.
"""


def run_partner_search(
    city: str,
    partner_type: str,
    channel_description: str,
    max_results: int = 20,
) -> tuple:
    """
    Use Claude with web_search tool to discover potential partners.
    Returns: (results_list, imported_count, duplicate_count)
    """
    user_prompt = f"""
Search the web for potential Bay Area Experiences referral partners.

CITY: {city}
PARTNER TYPE: {partner_type}
CHANNEL DESCRIPTION: {channel_description}
MAX RESULTS: {max_results}

Use multiple web searches to find a comprehensive list of matching
businesses in {city} and the surrounding Bay Area.

For hotels: search boutique hotels, B&Bs, and independent hotels
  with concierge desks that recommend local tours to guests.
For corporate: search tech companies 50–500 employees with HR managers
  or executive assistants who organise team outings.
For OTAs: search tour booking platforms and local activity operators.
For relocation: search relocation firms and corporate housing companies.

Return a JSON array of up to {max_results} businesses:
[
  {{
    "business_name": "...",
    "address": "...",
    "city": "{city}",
    "phone": "...",
    "website": "...",
    "contact_name": "...",
    "contact_email": "...",
    "contact_title": "...",
    "why_good_fit": "..."
  }}
]
"""

    try:
        import anthropic
        client  = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY', ''))
        messages = [{'role': 'user', 'content': user_prompt}]
        raw_text = ''

        # Agentic loop — web_search_20250305 may require multiple turns
        for _turn in range(8):
            response = client.beta.messages.create(
                betas      = ['web-search-2025-03-05'],
                model      = 'claude-sonnet-4-6',
                max_tokens = 4096,
                system     = SEARCH_SYSTEM,
                tools      = [{'type': 'web_search_20250305', 'name': 'web_search'}],
                messages   = messages,
            )
            log.info(
                '[PARTNER-SEARCH] turn=%d stop_reason=%s blocks=%s',
                _turn, response.stop_reason,
                [b.type for b in response.content],
            )

            if response.stop_reason == 'end_turn':
                # Only collect text on the final turn — intermediate turns may contain
                # stray '[' characters that would corrupt the JSON array extraction
                raw_text = ''.join(
                    b.text for b in response.content if b.type == 'text'
                )
                break

            if response.stop_reason == 'tool_use':
                # Continue conversation: append assistant turn + stub tool results
                messages.append({'role': 'assistant', 'content': response.content})
                tool_results = [
                    {'type': 'tool_result', 'tool_use_id': b.id, 'content': ''}
                    for b in response.content if b.type == 'tool_use'
                ]
                if not tool_results:
                    break
                messages.append({'role': 'user', 'content': tool_results})
                continue

            # max_tokens or other stop — attempt to use whatever text is present
            log.warning('[PARTNER-SEARCH] unexpected stop_reason=%s on turn=%d',
                        response.stop_reason, _turn)
            raw_text = ''.join(
                b.text for b in response.content if b.type == 'text'
            )
            break

        clean = _FENCE_RE.sub('', raw_text).strip()
        log.info('[PARTNER-SEARCH] raw_text length=%d', len(raw_text))

        # Extract the JSON array
        start = clean.find('[')
        end   = clean.rfind(']') + 1
        if start >= 0 and end > start:
            businesses = json.loads(clean[start:end])
        else:
            log.warning('[PARTNER-SEARCH] No JSON array found in response. raw_text=%r', raw_text[:500])
            businesses = []

    except Exception as e:
        log.error(f'[PARTNER-SEARCH] Claude call failed: {e}', exc_info=True)
        return None, 0, 0

    return _import_to_crm(businesses, partner_type, channel_description)


def _import_to_crm(
    businesses: list,
    partner_type: str,
    search_query: str,
) -> tuple:
    """
    Deduplicate against existing CRM and auto-import new prospects.
    Returns: (enriched_results, imported_count, duplicate_count)
    """
    from app.models import Partner
    from app.extensions import db
    from app.utils import generate_pk

    imported   = 0
    duplicates = 0
    results    = []
    now        = datetime.now(timezone.utc)

    for biz in businesses:
        name = (biz.get('business_name') or '').strip()
        city = (biz.get('city') or '').strip()
        if not name:
            continue

        # Deduplicate on normalised name + city
        existing = Partner.query.filter(
            db.func.lower(Partner.business_name) == name.lower(),
            db.func.lower(Partner.location_city)  == city.lower(),
        ).first()

        if existing:
            biz['_status']     = 'duplicate'
            biz['_partner_id'] = existing.partner_id
            duplicates += 1
        else:
            partner = Partner(
                partner_id             = generate_pk(),
                partner_type           = partner_type,
                business_name          = name,
                contact_name           = biz.get('contact_name') or None,
                contact_email          = biz.get('contact_email') or None,
                contact_phone          = biz.get('phone') or None,
                website                = biz.get('website') or None,
                location_city          = city,
                location_address       = biz.get('address') or None,
                status                 = 'prospect',
                discovery_source       = 'web_search',
                discovery_search_query = search_query,
                notes                  = biz.get('why_good_fit') or None,
                created_at             = now,
            )
            db.session.add(partner)
            biz['_status']     = 'imported'
            biz['_partner_id'] = partner.partner_id
            imported += 1

        biz['_contact_title'] = biz.get('contact_title', '')
        results.append(biz)

    db.session.commit()
    return results, imported, duplicates
