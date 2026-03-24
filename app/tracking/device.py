"""User-agent parsing — device type, browser, OS."""


def parse_device(ua_string: str) -> dict:
    """Return dict with keys: type, browser, os."""
    if not ua_string:
        return {'type': 'unknown', 'browser': None, 'os': None}
    try:
        from user_agents import parse
        ua = parse(ua_string)
        if ua.is_bot:
            device_type = 'bot'
        elif ua.is_mobile:
            device_type = 'mobile'
        elif ua.is_tablet:
            device_type = 'tablet'
        elif ua.is_pc:
            device_type = 'desktop'
        else:
            device_type = 'unknown'
        return {
            'type':    device_type,
            'browser': (ua.browser.family or None) and ua.browser.family[:80],
            'os':      (ua.os.family or None) and ua.os.family[:80],
        }
    except Exception:
        return {'type': 'unknown', 'browser': None, 'os': None}
