"""Referrer URL parsing and classification."""
from urllib.parse import urlparse

_ORGANIC = {
    'google.com', 'bing.com', 'yahoo.com', 'duckduckgo.com',
    'baidu.com', 'yandex.com', 'ask.com', 'ecosia.org',
}
_SOCIAL = {
    'facebook.com', 'instagram.com', 'twitter.com', 'x.com',
    'tiktok.com', 'linkedin.com', 'pinterest.com', 'youtube.com',
    'reddit.com', 'snapchat.com', 'threads.net',
}
_EMAIL = {
    'mail.google.com', 'outlook.live.com', 'mail.yahoo.com',
    'outlook.office365.com', 'webmail.',
}


def parse_domain(url: str):
    """Extract bare domain from a URL (strips www.)."""
    if not url:
        return None
    try:
        host = urlparse(url).netloc.lower()
        return host.removeprefix('www.') if host else None
    except Exception:
        return None


def classify_referrer(referrer: str) -> str:
    """Return: direct | organic | social | email | referral | unknown."""
    if not referrer:
        return 'direct'
    domain = parse_domain(referrer) or ''
    if not domain:
        return 'unknown'
    if any(domain == d or domain.endswith('.' + d) for d in _ORGANIC):
        return 'organic'
    if any(domain == d or domain.endswith('.' + d) for d in _SOCIAL):
        return 'social'
    if any(domain.startswith(d) or domain == d for d in _EMAIL):
        return 'email'
    return 'referral'
