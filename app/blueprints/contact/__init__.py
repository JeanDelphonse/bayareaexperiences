from flask import Blueprint

contact_bp = Blueprint('contact', __name__, url_prefix='/contact')

from app.blueprints.contact import routes  # noqa: F401, E402
