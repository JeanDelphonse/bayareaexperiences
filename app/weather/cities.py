"""Canonical registry of all 13 BAE serving cities with coordinates."""
import math

SERVING_CITIES = [
    {'name': 'San Francisco', 'display': 'San Francisco', 'state': 'CA',
     'lat': 37.7749, 'lng': -122.4194, 'timezone': 'America/Los_Angeles', 'is_default': True},
    {'name': 'San Jose',      'display': 'San Jose',      'state': 'CA',
     'lat': 37.3382, 'lng': -121.8863, 'timezone': 'America/Los_Angeles', 'is_default': False},
    {'name': 'Santa Cruz',    'display': 'Santa Cruz',    'state': 'CA',
     'lat': 36.9741, 'lng': -122.0308, 'timezone': 'America/Los_Angeles', 'is_default': False},
    {'name': 'Monterey',      'display': 'Monterey',      'state': 'CA',
     'lat': 36.6002, 'lng': -121.8947, 'timezone': 'America/Los_Angeles', 'is_default': False},
    {'name': 'Cupertino',     'display': 'Cupertino',     'state': 'CA',
     'lat': 37.3230, 'lng': -122.0322, 'timezone': 'America/Los_Angeles', 'is_default': False},
    {'name': 'Fremont',       'display': 'Fremont',       'state': 'CA',
     'lat': 37.5485, 'lng': -121.9886, 'timezone': 'America/Los_Angeles', 'is_default': False},
    {'name': 'Los Gatos',     'display': 'Los Gatos',     'state': 'CA',
     'lat': 37.2358, 'lng': -121.9624, 'timezone': 'America/Los_Angeles', 'is_default': False},
    {'name': 'Menlo Park',    'display': 'Menlo Park',    'state': 'CA',
     'lat': 37.4530, 'lng': -122.1817, 'timezone': 'America/Los_Angeles', 'is_default': False},
    {'name': 'Mountain View', 'display': 'Mountain View', 'state': 'CA',
     'lat': 37.3861, 'lng': -122.0839, 'timezone': 'America/Los_Angeles', 'is_default': False},
    {'name': 'Palo Alto',     'display': 'Palo Alto',     'state': 'CA',
     'lat': 37.4419, 'lng': -122.1430, 'timezone': 'America/Los_Angeles', 'is_default': False},
    {'name': 'Redwood City',  'display': 'Redwood City',  'state': 'CA',
     'lat': 37.4852, 'lng': -122.2364, 'timezone': 'America/Los_Angeles', 'is_default': False},
    {'name': 'Santa Clara',   'display': 'Santa Clara',   'state': 'CA',
     'lat': 37.3541, 'lng': -121.9552, 'timezone': 'America/Los_Angeles', 'is_default': False},
    {'name': 'Sunnyvale',     'display': 'Sunnyvale',     'state': 'CA',
     'lat': 37.3688, 'lng': -122.0363, 'timezone': 'America/Los_Angeles', 'is_default': False},
]

CITY_BY_NAME = {c['name']: c for c in SERVING_CITIES}

DEFAULT_CITY = next(c for c in SERVING_CITIES if c['is_default'])


def nearest_serving_city(lat: float, lng: float) -> dict:
    """Return the nearest serving city to a given lat/lng coordinate."""
    def dist(c):
        return math.sqrt((c['lat'] - lat) ** 2 + (c['lng'] - lng) ** 2)
    return min(SERVING_CITIES, key=dist)
