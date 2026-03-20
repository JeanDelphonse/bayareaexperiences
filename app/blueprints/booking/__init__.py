from flask import Blueprint

booking_bp = Blueprint('booking', __name__, )

from app.blueprints.booking import routes  # noqa: F401, E402
