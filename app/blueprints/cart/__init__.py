from flask import Blueprint

cart_bp = Blueprint('cart', __name__, )

from app.blueprints.cart import routes  # noqa: F401, E402
