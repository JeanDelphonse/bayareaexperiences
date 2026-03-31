from flask import Blueprint

loyalty_bp = Blueprint('loyalty', __name__)

from app.blueprints.loyalty import views  # noqa: F401, E402
