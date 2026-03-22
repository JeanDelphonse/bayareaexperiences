from flask import Blueprint

chat_bp = Blueprint('chat', __name__, url_prefix='/chat')

from app.blueprints.chat import routes  # noqa: F401, E402
