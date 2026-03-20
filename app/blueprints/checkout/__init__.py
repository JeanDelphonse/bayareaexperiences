from flask import Blueprint

checkout_bp = Blueprint('checkout', __name__, )

from app.blueprints.checkout import routes  # noqa: F401, E402
