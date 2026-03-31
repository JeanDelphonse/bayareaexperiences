from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
try:
    from flask_socketio import SocketIO
    _socketio_available = True
except ImportError:
    _socketio_available = False

db = SQLAlchemy()
login_manager = LoginManager()
bcrypt = Bcrypt()
mail = Mail()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://",
                  default_limits=[], headers_enabled=True)
socketio = SocketIO() if _socketio_available else None

login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'
