from flask import Blueprint

weather_bp = Blueprint('weather', __name__)

from app.blueprints.weather import views  # noqa
