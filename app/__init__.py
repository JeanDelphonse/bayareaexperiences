import logging
from logging.handlers import RotatingFileHandler
import os
import pymysql
pymysql.install_as_MySQLdb()
from flask import Flask, session, g
from config import config
from app.extensions import db, login_manager, bcrypt, mail, csrf, limiter
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

    # Tracking middleware
    from app.tracking.middleware import init_tracking
    init_tracking(app)

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

    return app
