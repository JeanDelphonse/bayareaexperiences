from flask import Blueprint

admin_bp = Blueprint('admin', __name__, url_prefix='/admin',
                     )

from app.blueprints.admin import routes    # noqa: F401, E402
from app.blueprints.admin import analytics  # noqa: F401, E402
