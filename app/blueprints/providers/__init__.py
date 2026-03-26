from flask import Blueprint

providers_bp = Blueprint('providers', __name__)

from app.blueprints.providers import views      # noqa: F401, E402
from app.blueprints.providers import dashboard  # noqa: F401, E402
from app.blueprints.providers import staff      # noqa: F401, E402
