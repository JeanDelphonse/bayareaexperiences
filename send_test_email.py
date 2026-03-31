"""
send_test_email.py — Send a test email using the app's Flask-Mail config.
Run from the project root: python send_test_email.py
"""
from app import create_app
from app.extensions import mail
from app.utils import send_email

app = create_app()

with app.app_context():
    print(f"MAIL_SERVER:          {app.config.get('MAIL_SERVER')}")
    print(f"MAIL_PORT:            {app.config.get('MAIL_PORT')}")
    print(f"MAIL_USE_TLS:         {app.config.get('MAIL_USE_TLS')}")
    print(f"MAIL_USERNAME:        {app.config.get('MAIL_USERNAME')}")
    print(f"MAIL_DEFAULT_SENDER:  {app.config.get('MAIL_DEFAULT_SENDER')}")
    print()

    recipient = 'valuemanager.management@gmail.com'
    print(f"Sending test email to {recipient} ...")

    try:
        send_email(
            mail,
            subject='BAE Mail Test — Flask-Mail is working',
            recipients=[recipient],
            body_html="""
<div style="font-family:sans-serif;max-width:480px;padding:24px;">
  <h2 style="color:#1A3557;">Bay Area Experiences — Mail Test</h2>
  <p>This is a test email sent via Flask-Mail to confirm SMTP is configured correctly.</p>
  <p style="color:#5A6A7A;font-size:13px;">Sent from send_test_email.py</p>
</div>
""",
        )
        print("Done — email sent successfully.")
    except Exception as e:
        print(f"FAILED: {e}")
