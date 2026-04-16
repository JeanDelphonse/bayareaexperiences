"""IP → country / region / city lookup via ip-api.com (free, no key required).

Rate limit: 45 req/min for the free tier.
Responses are cached in-process (LRU 512 entries) to avoid repeated lookups.
Returns empty dict on any failure — geo is best-effort only.

The lookup runs in a daemon thread with a 1-second hard join() timeout so that
DNS resolution hangs (which requests timeout= does NOT cover) can never block
the request handler long enough to trigger the host's reverse-proxy timeout.
"""
import threading
from functools import lru_cache

_LOOPBACK = {'0.0.0.0', '127.0.0.0', '127.0.0.1', '::1', '::0'}


@lru_cache(maxsize=512)
def ip_to_location(ip: str) -> tuple:
    """Return (country, region, city) — cached. Returns ('', '', '') on failure.

    Hard-capped at 1 second total including DNS — safe on hosts that block or
    rate-limit outbound HTTP (requests timeout= does not cover DNS resolution).
    """
    if not ip or ip in _LOOPBACK or ip.startswith('192.168.') or ip.startswith('10.'):
        return ('', '', '')

    result = [('', '', '')]

    def _fetch():
        try:
            import requests
            resp = requests.get(
                f'http://ip-api.com/json/{ip}',
                params={'fields': 'status,country,regionName,city'},
                timeout=0.8,
            )
            data = resp.json()
            if data.get('status') == 'success':
                result[0] = (
                    data.get('country') or '',
                    data.get('regionName') or '',
                    data.get('city') or '',
                )
        except Exception:
            pass

    t = threading.Thread(target=_fetch, daemon=True)
    t.start()
    t.join(timeout=1.0)   # hard cap — covers DNS hang that requests cannot
    return result[0]


def get_location(ip: str) -> dict:
    """Convenience wrapper returning a dict."""
    country, region, city = ip_to_location(ip)
    return {'country': country or None, 'region': region or None, 'city': city or None}
