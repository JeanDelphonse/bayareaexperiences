import logging
from logging.handlers import RotatingFileHandler
import os
import pymysql
pymysql.install_as_MySQLdb()
from flask import Flask, session, g
from config import config
from app.extensions import db, login_manager, bcrypt, mail, csrf, limiter, socketio
from app.models import CartItem


def create_app(config_name='default'):
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config.from_object(config[config_name])

    # Extensions
    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    if socketio is not None:
        socketio.init_app(app,
            cors_allowed_origins='*',
            async_mode='threading',
            logger=False,
            engineio_logger=False,
        )

    # Blueprints
    from app.blueprints.main   import main_bp
    from app.blueprints.auth   import auth_bp
    from app.blueprints.booking import booking_bp
    from app.blueprints.cart   import cart_bp
    from app.blueprints.checkout import checkout_bp
    from app.blueprints.account import account_bp
    from app.blueprints.admin  import admin_bp
    from app.blueprints.contact  import contact_bp
    from app.blueprints.chat     import chat_bp
    from app.blueprints.tracking import tracking_bp
    from app.blueprints.providers import providers_bp
    from app.blueprints.payments import payments_bp
    from app.blueprints.reviews import reviews_bp
    from app.blueprints.itinerary import itinerary_bp
    from app.blueprints.staff import staff_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(booking_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(checkout_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(contact_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(tracking_bp)
    app.register_blueprint(providers_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(itinerary_bp)
    app.register_blueprint(staff_bp)

    # Tracking middleware (analytics)
    from app.tracking.middleware import init_tracking
    init_tracking(app)

    # GPS SocketIO event handlers — import to register decorators
    if socketio is not None:
        from app.blueprints.tracking import socketio_handlers  # noqa: F401

    # Template filters
    @app.template_filter('format_number')
    def format_number_filter(value):
        try:
            return '{:,}'.format(int(value))
        except (TypeError, ValueError):
            return value

    # Cart count context processor
    @app.context_processor
    def inject_cart_count():
        from flask_login import current_user
        count = 0
        if current_user.is_authenticated:
            count = CartItem.query.filter_by(user_id=current_user.user_id).count()
        else:
            count = len(session.get('cart', []))
        return dict(cart_count=count)

    # Logging — attach file handler to root logger so all named loggers write to it
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    file_handler = RotatingFileHandler(os.path.join(log_dir, 'bae_app.log'), maxBytes=1_000_000, backupCount=5)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter('%(asctime)s %(name)s %(levelname)s: %(message)s'))
    logging.getLogger().addHandler(file_handler)
    logging.getLogger().setLevel(logging.INFO)
    app.logger.setLevel(logging.INFO)

    with app.app_context():
        db.create_all()
        # GPS migration: add tracking_enabled to bookings if not yet present
        try:
            from sqlalchemy import text, inspect as sa_inspect
            _insp = sa_inspect(db.engine)
            _cols = [c['name'] for c in _insp.get_columns('bookings')]
            if 'tracking_enabled' not in _cols:
                with db.engine.connect() as _conn:
                    _conn.execute(text(
                        'ALTER TABLE bookings ADD COLUMN tracking_enabled BOOLEAN NOT NULL DEFAULT 1'
                    ))
                    _conn.commit()
        except Exception:
            pass

        # UserPrefs migration: add preference_source to booking_preferences if not yet present
        try:
            from sqlalchemy import text, inspect as sa_inspect
            _insp = sa_inspect(db.engine)
            if 'booking_preferences' in _insp.get_table_names():
                _bp_cols = [c['name'] for c in _insp.get_columns('booking_preferences')]
                if 'preference_source' not in _bp_cols:
                    with db.engine.connect() as _conn:
                        _conn.execute(text(
                            "ALTER TABLE booking_preferences ADD COLUMN preference_source "
                            "VARCHAR(20) NOT NULL DEFAULT 'booking_step'"
                        ))
                        _conn.commit()
        except Exception:
            pass

    return app
