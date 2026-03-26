"""Event data fetching — Ticketmaster (primary) + Eventbrite (secondary)."""
import os
import logging
import requests

log = logging.getLogger('itinerary')

TM_BASE = 'https://app.ticketmaster.com/discovery/v2/events.json'
EB_BASE = 'https://www.eventbriteapi.com/v3/events/search/'

RELEVANT_SEGMENTS = ['Music', 'Arts & Theatre', 'Family', 'Sports', 'Miscellaneous']

EXCLUDE_FOR_EXPERIENCE = {
    'airport-transfer':      ['Sports'],
    'corporate-team-outing': ['Family'],
    'celebration-tour':      [],
}

CITY_STATE = {
    'San Francisco': 'CA', 'San Jose': 'CA', 'Santa Cruz': 'CA',
    'Monterey': 'CA', 'Cupertino': 'CA', 'Fremont': 'CA',
    'Los Gatos': 'CA', 'Menlo Park': 'CA', 'Mountain View': 'CA',
    'Palo Alto': 'CA', 'Redwood City': 'CA', 'Santa Clara': 'CA',
    'Sunnyvale': 'CA',
}


def fetch_ticketmaster_events(city: str, state_code: str, tour_date: str,
                               experience_slug: str = None) -> list:
    api_key = os.environ.get('TICKETMASTER_API_KEY', '')
    if not api_key:
        return []

    start = f'{tour_date}T00:00:00Z'
    end   = f'{tour_date}T23:59:59Z'

    params = {
        'apikey':        api_key,
        'city':          city,
        'stateCode':     state_code,
        'startDateTime': start,
        'endDateTime':   end,
        'size':          10,
        'sort':          'relevance,desc',
    }

    try:
        resp = requests.get(TM_BASE, params=params, timeout=8)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning(f'Ticketmaster fetch failed: {e}')
        return []

    events = []
    for ev in data.get('_embedded', {}).get('events', []):
        segment = ''
        try:
            segment = ev['classifications'][0]['segment']['name']
        except (KeyError, IndexError):
            pass

        if segment and segment not in RELEVANT_SEGMENTS:
            continue
        exclude = EXCLUDE_FOR_EXPERIENCE.get(experience_slug, [])
        if segment in exclude:
            continue

        venue_name = ''
        venue_city = ''
        try:
            venue_name = ev['_embedded']['venues'][0]['name']
            venue_city = ev['_embedded']['venues'][0]['city']['name']
        except (KeyError, IndexError):
            pass

        events.append({
            'source':   'ticketmaster',
            'name':     ev.get('name', ''),
            'venue':    venue_name,
            'city':     venue_city or city,
            'date':     ev.get('dates', {}).get('start', {}).get('localDate', tour_date),
            'category': segment,
            'url':      ev.get('url', ''),
        })

        if len(events) >= 5:
            break

    return events


EB_CATEGORIES = '103,110,113,101,104'  # Arts, Food, Community, Music, Outdoors


def fetch_eventbrite_events(city: str, state_code: str, tour_date: str) -> list:
    api_key = os.environ.get('EVENTBRITE_API_KEY', '')
    if not api_key:
        return []

    address = f'{city}, {state_code}'
    start   = f'{tour_date}T00:00:00'
    end     = f'{tour_date}T23:59:59'

    headers = {'Authorization': f'Bearer {api_key}'}
    params  = {
        'location.address':       address,
        'location.within':        '20mi',
        'start_date.range_start': start,
        'start_date.range_end':   end,
        'categories':             EB_CATEGORIES,
        'expand':                 'venue',
        'page_size':              5,
        'sort_by':                'best',
    }

    try:
        resp = requests.get(EB_BASE, headers=headers, params=params, timeout=8)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning(f'Eventbrite fetch failed: {e}')
        return []

    events = []
    for ev in data.get('events', []):
        venue_name = ''
        try:
            venue_name = ev['venue']['name']
        except (KeyError, TypeError):
            pass

        events.append({
            'source':   'eventbrite',
            'name':     ev.get('name', {}).get('text', ''),
            'venue':    venue_name,
            'city':     city,
            'date':     tour_date,
            'category': 'Community Event',
            'url':      ev.get('url', ''),
        })

    return events


def get_local_events(city: str, state_code: str, tour_date: str,
                     experience_slug: str = None) -> list:
    """Combine Ticketmaster + Eventbrite, deduplicate, return up to 5."""
    tm = fetch_ticketmaster_events(city, state_code, tour_date, experience_slug)
    eb = fetch_eventbrite_events(city, state_code, tour_date)

    seen, unique = set(), []
    for ev in tm + eb:
        key = ev['name'].lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(ev)

    return unique[:5]
