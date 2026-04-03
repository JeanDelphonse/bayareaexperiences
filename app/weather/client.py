"""Open-Meteo weather client with 30-minute in-process cache."""
import logging
import os
import time
from datetime import datetime

import requests

log = logging.getLogger('weather')

OPEN_METEO_URL = 'https://api.open-meteo.com/v1/forecast'

WMO_CODES = {
    0:  ('Clear', '☀️'),
    1:  ('Mostly Clear', '🌤️'),
    2:  ('Partly Cloudy', '⛅'),
    3:  ('Overcast', '☁️'),
    45: ('Foggy', '🌫️'),
    48: ('Icy Fog', '🌫️'),
    51: ('Light Drizzle', '🌦️'),
    53: ('Drizzle', '🌧️'),
    55: ('Heavy Drizzle', '🌧️'),
    61: ('Light Rain', '🌧️'),
    63: ('Rain', '🌧️'),
    65: ('Heavy Rain', '🌧️'),
    71: ('Light Snow', '❄️'),
    73: ('Snow', '❄️'),
    75: ('Heavy Snow', '❄️'),
    80: ('Rain Showers', '🌦️'),
    81: ('Heavy Showers', '🌧️'),
    82: ('Violent Showers', '⛈️'),
    85: ('Snow Showers', '🌨️'),
    95: ('Thunderstorm', '⛈️'),
    96: ('Thunderstorm + Hail', '⛈️'),
    99: ('Thunderstorm + Hail', '⛈️'),
}


def _wmo(code: int) -> tuple:
    return WMO_CODES.get(code, ('Unknown', '🌡️'))


# Simple in-process cache: { key: (timestamp, data) }
_cache: dict = {}


def _cache_ttl() -> int:
    return int(os.environ.get('WEATHER_CACHE_TTL_SECONDS', 1800))


def _fetch_timeout() -> int:
    return int(os.environ.get('WEATHER_FETCH_TIMEOUT_SECONDS', 6))


def _cache_get(key):
    if key in _cache:
        ts, data = _cache[key]
        if time.time() - ts < _cache_ttl():
            return data
        del _cache[key]
    return None


def _cache_set(key, data):
    _cache[key] = (time.time(), data)


def fetch_forecast(lat: float, lng: float, days: int = 5) -> dict:
    """
    Fetch a forecast for the given coordinates.
    Returns a structured dict with current conditions and daily forecast.
    Cached per coordinate pair for WEATHER_CACHE_TTL_SECONDS (default 30 min).
    Never raises — returns empty dict on any failure.
    """
    key = f'{lat:.4f},{lng:.4f}'
    cached = _cache_get(key)
    if cached:
        return cached

    params = {
        'latitude':   lat,
        'longitude':  lng,
        'current_weather': True,
        'daily': [
            'temperature_2m_max',
            'temperature_2m_min',
            'precipitation_probability_max',
            'weathercode',
        ],
        'temperature_unit': 'fahrenheit',
        'wind_speed_unit':  'mph',
        'timezone':         'America/Los_Angeles',
        'forecast_days':    days,
    }

    try:
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=_fetch_timeout())
        resp.raise_for_status()
        raw = resp.json()
    except Exception as e:
        log.warning(f'Open-Meteo fetch failed: {e}')
        return {}

    cw = raw.get('current_weather', {})
    cond_text, cond_emoji = _wmo(int(cw.get('weathercode', 0)))
    current = {
        'temp_f':    round(cw.get('temperature', 0)),
        'condition': cond_text,
        'emoji':     cond_emoji,
        'wind_mph':  round(cw.get('windspeed', 0)),
        'is_day':    bool(cw.get('is_day', 1)),
    }

    daily_raw = raw.get('daily', {})
    dates     = daily_raw.get('time', [])
    highs     = daily_raw.get('temperature_2m_max', [])
    lows      = daily_raw.get('temperature_2m_min', [])
    rain_pct  = daily_raw.get('precipitation_probability_max', [])
    wcodes    = daily_raw.get('weathercode', [])

    days_list = []
    for i, date_str in enumerate(dates):
        dt_obj   = datetime.strptime(date_str, '%Y-%m-%d')
        day_name = dt_obj.strftime('%a')
        day_short = f'{dt_obj.month}/{dt_obj.day}'
        wcode    = int(wcodes[i]) if i < len(wcodes) else 0
        c_text, c_emoji = _wmo(wcode)
        days_list.append({
            'date':      date_str,
            'day_name':  day_name,
            'day_short': day_short,
            'high_f':    round(highs[i]) if i < len(highs) else None,
            'low_f':     round(lows[i])  if i < len(lows)  else None,
            'rain_pct':  int(rain_pct[i]) if i < len(rain_pct) else 0,
            'condition': c_text,
            'emoji':     c_emoji,
        })

    result = {'current': current, 'daily': days_list}
    _cache_set(key, result)
    return result


def fetch_forecast_for_city(city: dict, days: int = 5) -> dict:
    """Convenience wrapper — accepts a city dict from SERVING_CITIES."""
    return fetch_forecast(city['lat'], city['lng'], days)


def fetch_forecast_for_date(lat: float, lng: float, target_date: str) -> dict | None:
    """
    Fetch a 7-day forecast and return only the entry matching target_date.
    target_date format: 'YYYY-MM-DD'
    Returns a single day dict or None if date not in forecast window.
    """
    forecast = fetch_forecast(lat, lng, days=7)
    if not forecast:
        return None
    for day in forecast.get('daily', []):
        if day['date'] == target_date:
            return day
    return None
