import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

print("DATABASE_URL:", os.environ.get('DATABASE_URL', 'NOT SET'))

try:
    import pymysql
    print("PyMySQL: OK")
except Exception as e:
    print("PyMySQL ERROR:", e)

try:
    pymysql.install_as_MySQLdb()
    url = os.environ.get('DATABASE_URL', '')
    # parse host/user/pass/db from URL
    from urllib.parse import urlparse
    u = urlparse(url)
    conn = pymysql.connect(host=u.hostname, user=u.username, password=u.password, database=u.path.lstrip('/'))
    print("MySQL connection: OK")
    conn.close()
except Exception as e:
    print("MySQL connection ERROR:", e)

try:
    from app import create_app
    app = create_app('production')
    print("create_app production: OK")
except Exception as e:
    print("create_app ERROR:", e)
