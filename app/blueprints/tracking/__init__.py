from flask import Blueprint

tracking_bp = Blueprint('tracking', __name__)

from app.blueprints.tracking import views  # noqa: F401, E402
