import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True

    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'localhost')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 25))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'False') == 'True'
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'False') == 'True'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or None
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') or None
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@bayareaexperiences.com')
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'valuemanager.management@gmail.com')

    STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

    RECAPTCHA_SITE_KEY = os.environ.get('RECAPTCHA_SITE_KEY', '')
    RECAPTCHA_SECRET_KEY = os.environ.get('RECAPTCHA_SECRET_KEY', '')

    ANTHROPIC_API_KEY  = os.environ.get('ANTHROPIC_API_KEY', '')
    CHAT_MAX_TOKENS    = int(os.environ.get('CHAT_MAX_TOKENS', 1024))
    CHAT_HISTORY_LIMIT = int(os.environ.get('CHAT_HISTORY_LIMIT', 10))
    CHAT_ENABLED       = os.environ.get('CHAT_ENABLED', 'True') == 'True'

    _raw_page_size = os.environ.get('ADMIN_PAGE_SIZE', '20')
    ADMIN_PAGE_SIZE = int(_raw_page_size) if _raw_page_size in ('10', '20', '50') else 20

    # Analytics / Tracking
    TRACKING_ENABLED         = os.environ.get('TRACKING_ENABLED', 'True') == 'True'
    TRACKING_SESSION_TIMEOUT = int(os.environ.get('TRACKING_SESSION_TIMEOUT', 1800))   # seconds
    TRACKING_RETENTION_DAYS  = int(os.environ.get('TRACKING_RETENTION_DAYS', 90))
    GEOIP_PROVIDER           = os.environ.get('GEOIP_PROVIDER', 'ip-api')

    # Marketplace / Provider tiers
    STRIPE_PRO_MONTHLY_PRICE_ID = os.environ.get('STRIPE_PRO_MONTHLY_PRICE_ID', '')
    STRIPE_PRO_ANNUAL_PRICE_ID  = os.environ.get('STRIPE_PRO_ANNUAL_PRICE_ID', '')
    FREE_TIER_COMMISSION_RATE   = float(os.environ.get('FREE_TIER_COMMISSION_RATE', '20'))
    PRO_TIER_PROCESSING_RATE    = float(os.environ.get('PRO_TIER_PROCESSING_RATE', '5'))
    PRO_TIER_MONTHLY_PRICE      = float(os.environ.get('PRO_TIER_MONTHLY_PRICE', '149'))
    PRO_TIER_ANNUAL_PRICE       = float(os.environ.get('PRO_TIER_ANNUAL_PRICE', '999'))


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DEV_DATABASE_URL', 'sqlite:///bae_dev.db')


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 1800,
    }


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}
