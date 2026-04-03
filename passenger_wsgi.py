# passenger_wsgi.py — place at GoDaddy cPanel domain root
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from werkzeug.middleware.proxy_fix import ProxyFix

application = create_app('production')
application.wsgi_app = ProxyFix(application.wsgi_app, x_for=1, x_proto=1, x_host=1)
