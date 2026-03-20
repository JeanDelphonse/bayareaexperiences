from flask import Blueprint

account_bp = Blueprint('account', __name__, )

from app.blueprints.account import routes  # noqa: F401, E402
