"""IP → country / region / city lookup via ip-api.com (free, no key required).

Rate limit: 45 req/min for the free tier.
Responses are cached in-process (LRU 512 entries) to avoid repeated lookups.
Returns empty dict on any failure — geo is best-effort only.
"""
from functools import lru_cache

_LOOPBACK = {'0.0.0.0', '127.0.0.0', '127.0.0.1', '::1', '::0'}


@lru_cache(maxsize=512)
def ip_to_location(ip: str) -> tuple:
    """Return (country, region, city) — cached. Returns ('', '', '') on failure."""
    if not ip or ip in _LOOPBACK or ip.startswith('192.168.') or ip.startswith('10.'):
        return ('', '', '')
    try:
        import requests
        resp = requests.get(
            f'http://ip-api.com/json/{ip}',
            params={'fields': 'status,country,regionName,city'},
            timeout=2,
        )
        data = resp.json()
        if data.get('status') == 'success':
            return (
                data.get('country') or '',
                data.get('regionName') or '',
                data.get('city') or '',
            )
    except Exception:
        pass
    return ('', '', '')


def get_location(ip: str) -> dict:
    """Convenience wrapper returning a dict."""
    country, region, city = ip_to_location(ip)
    return {'country': country or None, 'region': region or None, 'city': city or None}
