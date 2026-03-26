from flask import Blueprint

itinerary_bp = Blueprint('itinerary', __name__)

from app.blueprints.itinerary import views  # noqa
