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
    from app.blueprints.loyalty import loyalty_bp
    from app.blueprints.weather import weather_bp

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
    app.register_blueprint(loyalty_bp)
    app.register_blueprint(weather_bp)

    # Tracking middleware (analytics)
    from app.tracking.middleware import init_tracking
    init_tracking(app)

    # GPS SocketIO event handlers — import to register decorators
    if socketio is not None:
        from app.blueprints.tracking import socketio_handlers  # noqa: F401

    # CSS cache-busting: expose mtime of custom.css as a Jinja global
    _css_path = os.path.join(app.static_folder, 'css', 'custom.css')
    try:
        app.jinja_env.globals['css_v'] = int(os.path.getmtime(_css_path))
    except OSError:
        app.jinja_env.globals['css_v'] = 1

    # Template filters
    @app.template_filter('format_number')
    def format_number_filter(value):
        try:
            return '{:,}'.format(int(value))
        except (TypeError, ValueError):
            return value

    import json as _json
    @app.template_filter('from_json')
    def from_json_filter(value):
        try:
            return _json.loads(value) if value else {}
        except (ValueError, TypeError):
            return {}

    # Inject today's date for templates
    @app.context_processor
    def inject_today():
        from datetime import date
        return dict(today=date.today())

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

        # Loyalty migrations: add columns to users and bookings if not yet present
        try:
            from sqlalchemy import text, inspect as sa_inspect
            _insp = sa_inspect(db.engine)
            _ucols = [c['name'] for c in _insp.get_columns('users')]
            with db.engine.connect() as _conn:
                if 'is_vip' not in _ucols:
                    _conn.execute(text('ALTER TABLE users ADD COLUMN is_vip BOOLEAN NOT NULL DEFAULT 0'))
                if 'total_referral_credit_balance' not in _ucols:
                    _conn.execute(text(
                        'ALTER TABLE users ADD COLUMN total_referral_credit_balance DECIMAL(8,2) NOT NULL DEFAULT 0.00'
                    ))
                _bcols = [c['name'] for c in _insp.get_columns('bookings')]
                if 'discount_code_id' not in _bcols:
                    _conn.execute(text('ALTER TABLE bookings ADD COLUMN discount_code_id VARCHAR(9) NULL'))
                if 'discount_amount' not in _bcols:
                    _conn.execute(text('ALTER TABLE bookings ADD COLUMN discount_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00'))
                if 'referral_credit_applied' not in _bcols:
                    _conn.execute(text('ALTER TABLE bookings ADD COLUMN referral_credit_applied DECIMAL(8,2) NOT NULL DEFAULT 0.00'))
                _conn.commit()
        except Exception:
            pass

        # Discount migrations: add promotional discount columns to experiences
        try:
            from sqlalchemy import text, inspect as sa_inspect
            _insp = sa_inspect(db.engine)
            _ecols = [c['name'] for c in _insp.get_columns('experiences')]
            with db.engine.connect() as _conn:
                if 'discount_percent' not in _ecols:
                    _conn.execute(text("ALTER TABLE experiences ADD COLUMN discount_percent ENUM('10','15','20') NULL"))
                if 'discounted_price' not in _ecols:
                    _conn.execute(text('ALTER TABLE experiences ADD COLUMN discounted_price DECIMAL(10,2) NULL'))
                if 'discount_active' not in _ecols:
                    _conn.execute(text('ALTER TABLE experiences ADD COLUMN discount_active BOOLEAN NOT NULL DEFAULT 0'))
                if 'discount_label' not in _ecols:
                    _conn.execute(text('ALTER TABLE experiences ADD COLUMN discount_label VARCHAR(80) NULL'))
                if 'discount_start' not in _ecols:
                    _conn.execute(text('ALTER TABLE experiences ADD COLUMN discount_start DATETIME NULL'))
                if 'discount_end' not in _ecols:
                    _conn.execute(text('ALTER TABLE experiences ADD COLUMN discount_end DATETIME NULL'))
                _conn.commit()
        except Exception:
            pass

        # Partner v1.1 migration: website, location_address, discovery columns
        try:
            from sqlalchemy import text, inspect as sa_inspect
            _insp  = sa_inspect(db.engine)
            _dialect = db.engine.dialect.name
            if 'partners' in _insp.get_table_names():
                _pcols = [c['name'] for c in _insp.get_columns('partners')]
                with db.engine.connect() as _conn:
                    if 'website' not in _pcols:
                        _conn.execute(text('ALTER TABLE partners ADD COLUMN website VARCHAR(500) NULL'))
                    if 'location_address' not in _pcols:
                        _conn.execute(text('ALTER TABLE partners ADD COLUMN location_address VARCHAR(300) NULL'))
                    if 'discovery_source' not in _pcols:
                        if _dialect == 'mysql':
                            _conn.execute(text(
                                "ALTER TABLE partners ADD COLUMN discovery_source "
                                "ENUM('web_search','manual','referral') NOT NULL DEFAULT 'manual'"
                            ))
                        else:
                            _conn.execute(text(
                                "ALTER TABLE partners ADD COLUMN discovery_source VARCHAR(20) NOT NULL DEFAULT 'manual'"
                            ))
                    if 'discovery_search_query' not in _pcols:
                        _conn.execute(text('ALTER TABLE partners ADD COLUMN discovery_search_query TEXT NULL'))
                    _conn.commit()
            if 'partner_outreach' in _insp.get_table_names():
                _ocols = [c['name'] for c in _insp.get_columns('partner_outreach')]
                # Make run_id nullable if not already (MySQL only — SQLite ignores NOT NULL on FK)
                if _dialect == 'mysql':
                    with db.engine.connect() as _conn:
                        try:
                            _conn.execute(text(
                                'ALTER TABLE partner_outreach MODIFY COLUMN run_id CHAR(9) NULL'
                            ))
                            _conn.commit()
                        except Exception:
                            pass
        except Exception:
            pass

        # Agents migration: is_mystery on experiences, mystery fields on bookings
        try:
            from sqlalchemy import text, inspect as sa_inspect
            _insp = sa_inspect(db.engine)
            _dialect = db.engine.dialect.name
            _ecols = [c['name'] for c in _insp.get_columns('experiences')]
            _bcols = [c['name'] for c in _insp.get_columns('bookings')]
            with db.engine.connect() as _conn:
                if 'is_mystery' not in _ecols:
                    _conn.execute(text(
                        'ALTER TABLE experiences ADD COLUMN is_mystery BOOLEAN NOT NULL DEFAULT 0'
                    ))
                if 'mystery_vibe' not in _bcols:
                    if _dialect == 'mysql':
                        _conn.execute(text(
                            "ALTER TABLE bookings ADD COLUMN mystery_vibe "
                            "ENUM('adventure','foodie','culture','relax','celebrate') NULL"
                        ))
                    else:
                        _conn.execute(text(
                            "ALTER TABLE bookings ADD COLUMN mystery_vibe VARCHAR(20) NULL"
                        ))
                if 'mystery_reveal_sent_at' not in _bcols:
                    _conn.execute(text(
                        'ALTER TABLE bookings ADD COLUMN mystery_reveal_sent_at DATETIME NULL'
                    ))
                _conn.commit()
        except Exception:
            pass

        # Sample itinerary migration: add sample_itinerary + sample_itinerary_at to experiences
        try:
            from sqlalchemy import text, inspect as sa_inspect
            _insp = sa_inspect(db.engine)
            _ecols = [c['name'] for c in _insp.get_columns('experiences')]
            with db.engine.connect() as _conn:
                if 'sample_itinerary' not in _ecols:
                    _conn.execute(text('ALTER TABLE experiences ADD COLUMN sample_itinerary TEXT NULL'))
                if 'sample_itinerary_at' not in _ecols:
                    _conn.execute(text('ALTER TABLE experiences ADD COLUMN sample_itinerary_at DATETIME NULL'))
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
