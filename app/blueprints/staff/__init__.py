from flask import Blueprint

staff_bp = Blueprint('staff_portal', __name__)

from app.blueprints.staff import views  # noqa: F401, E402
