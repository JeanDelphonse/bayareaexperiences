"""AJAX weather endpoint for homepage widget."""
from flask import request, jsonify, current_app

from app.blueprints.weather import weather_bp
from app.weather.client import fetch_forecast_for_city
from app.weather.cities import CITY_BY_NAME, DEFAULT_CITY, nearest_serving_city


@weather_bp.route('/weather/forecast')
def forecast():
    """
    AJAX endpoint for homepage weather widget.
    Accepts: ?city=San+Francisco  OR  ?lat=37.77&lng=-122.41
    Returns: JSON forecast dict.
    Cached 30 min server-side.
    """
    if not current_app.config.get('WEATHER_ENABLED', True):
        return jsonify({'error': 'Weather disabled'}), 503

    city_name = request.args.get('city', '').strip()
    lat_str   = request.args.get('lat', '')
    lng_str   = request.args.get('lng', '')

    if city_name and city_name in CITY_BY_NAME:
        city = CITY_BY_NAME[city_name]
    elif lat_str and lng_str:
        try:
            city = nearest_serving_city(float(lat_str), float(lng_str))
        except ValueError:
            city = DEFAULT_CITY
    else:
        city = DEFAULT_CITY

    data = fetch_forecast_for_city(city)
    if not data:
        return jsonify({'error': 'Weather unavailable'}), 503

    return jsonify({
        'city':    city['display'],
        'current': data['current'],
        'daily':   data['daily'],
    })
