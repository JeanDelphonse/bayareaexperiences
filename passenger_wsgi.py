# passenger_wsgi.py — place at GoDaddy cPanel domain root
import eventlet
eventlet.monkey_patch()

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from app.extensions import socketio
application = create_app('production')
