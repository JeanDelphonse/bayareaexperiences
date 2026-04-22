"""
Provider account helpers: temp password generation and welcome email.
Called from the admin provider create / resend-credentials flows.
"""
import secrets
import logging
from datetime import datetime, timezone

from flask import url_for

from app.extensions import db, bcrypt
from app.utils import send_email

log = logging.getLogger('provider_account')


def generate_temp_password(length: int = 12) -> str:
    return secrets.token_urlsafe(length)[:length]


def send_provider_welcome_email(provider, user, temp_password: str) -> None:
    login_url   = url_for('auth.login', _external=True)
    profile_url = url_for('providers.dashboard_profile', _external=True)

    subject = (
        f'Welcome to Bay Area Experiences, {user.first_name} — '
        f'your account is ready'
    )

    body_text = f"""
Hi {user.first_name},

Your Bay Area Experiences provider account has been created.
You can now sign in to your provider portal and start listing
your experiences on our platform.

YOUR LOGIN DETAILS
  Login page : {login_url}
  Email      : {user.email}
  Password   : {temp_password}

This is a temporary password. Once you sign in, please
visit your profile page to set a permanent password:
  {profile_url}

BUSINESS NAME: {provider.business_name}

If you have any questions, reply to this email or
call us at (408) 831-2101.

— Jean Delphonse
  Bay Area Experiences
  bayareaexperiences.com
"""

    body_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset='UTF-8'>
<style>
  body  {{ font-family:Arial,sans-serif;color:#1C1C1E;background:#F2F5F8;margin:0;padding:0; }}
  .wrap {{ max-width:560px;margin:32px auto;background:#fff;border-radius:12px;overflow:hidden; }}
  .hdr  {{ background:#1A3557;padding:28px 32px; }}
  .hdr h1 {{ color:#C9952A;font-size:20px;margin:0; }}
  .hdr p  {{ color:rgba(255,255,255,.65);font-size:13px;margin:4px 0 0; }}
  .body {{ padding:28px 32px; }}
  .creds {{ background:#EFF4F9;border-radius:10px;padding:18px 20px;margin:20px 0; }}
  .creds p {{ margin:6px 0;font-size:14px; }}
  .label {{ color:#5A6A7A;font-size:11px;text-transform:uppercase;letter-spacing:.08em; }}
  .value {{ font-weight:600;color:#1A3557;font-size:15px;font-family:monospace; }}
  .cta  {{ display:inline-block;background:#1A3557;color:#fff;text-decoration:none;
           padding:12px 28px;border-radius:8px;font-size:14px;font-weight:500;margin:16px 0 4px; }}
  .warn {{ background:#FDF6EC;border:0.5px solid #E8D5A3;border-radius:8px;
           padding:12px 16px;font-size:13px;color:#8B6419;margin:16px 0; }}
  .ftr  {{ background:#F2F5F8;padding:16px 32px;font-size:12px;color:#5A6A7A;
           border-top:1px solid #D0D8E0; }}
</style>
</head>
<body>
<div class='wrap'>
  <div class='hdr'>
    <h1>Bay Area Experiences</h1>
    <p>Provider Portal — Account Created</p>
  </div>
  <div class='body'>
    <p style='font-size:16px;'>Hi {user.first_name},</p>
    <p>Your provider account for <strong>{provider.business_name}</strong>
    has been created. Here are your login details:</p>
    <div class='creds'>
      <p><span class='label'>Login page</span><br>
         <a href='{login_url}' style='color:#2E7D8C;font-size:13px;'>{login_url}</a></p>
      <p><span class='label'>Email (username)</span><br>
         <span class='value'>{user.email}</span></p>
      <p><span class='label'>Temporary password</span><br>
         <span class='value'>{temp_password}</span></p>
    </div>
    <div class='warn'>
      &#9888;&nbsp; This is a temporary password. Please change it as soon as you sign in.
    </div>
    <a href='{login_url}' class='cta'>Sign in to your portal &rarr;</a>
    <p style='font-size:13px;color:#5A6A7A;margin-top:20px;'>
      After signing in, you will be directed to your profile page to set a
      permanent password. If you have any questions, reply to this email or
      call <strong>(408) 831-2101</strong>.
    </p>
  </div>
  <div class='ftr'>
    Bay Area Experiences &nbsp;·&nbsp; bayareaexperiences.com &nbsp;·&nbsp; (408) 831-2101
  </div>
</div>
</body></html>"""

    from app.extensions import mail
    send_email(mail, subject, [user.email], body_html, body_text)


def reset_provider_credentials(provider) -> str:
    """
    Generate a new temp password, update the user's hash, set must_change_password=True,
    send welcome email. Returns the new temp password (for logging only).
    """
    user          = provider.user
    temp_password = generate_temp_password()

    user.password_hash        = bcrypt.generate_password_hash(temp_password).decode('utf-8')
    user.must_change_password = True
    user.updated_at           = datetime.now(timezone.utc)

    try:
        send_provider_welcome_email(provider, user, temp_password)
    except Exception as e:
        log.error(f'Welcome email failed for {user.email}: {e}')

    return temp_password
