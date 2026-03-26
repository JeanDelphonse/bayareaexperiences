import os
from flask import url_for, current_app
from flask_mail import Message
from app.extensions import mail


def send_feedback_request(booking, token):
    """Send the post-tour feedback email. Returns True on success."""
    try:
        feedback_url = url_for('reviews.feedback_form', token=token.token, _external=True)

        subject = f'How was your Bay Area Experience? (we\'d love to know)'

        html_body = f'''<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; max-width: 580px; margin: auto; color: #1C1C1E;">
  <div style="background:#1A3557; padding:24px; border-radius:8px 8px 0 0; text-align:center;">
    <h2 style="color:#fff; margin:0; font-size:20px;">Bay Area Experiences</h2>
    <p style="color:#F5C97A; margin:6px 0 0; font-size:13px;">{booking.experience.name}</p>
  </div>
  <div style="background:#f8f9fa; padding:28px; border:1px solid #dee2e6;">
    <p style="font-size:16px; margin:0 0 16px;">Hi {booking.guest_first_name},</p>
    <p style="font-size:15px; line-height:1.7; margin:0 0 16px;">
      Thank you for spending the day with us on the <strong>{booking.experience.name}</strong> experience.
      We hope it was everything you were hoping for — and then some.
    </p>
    <p style="font-size:15px; line-height:1.7; margin:0 0 24px;">We have just one question for you:</p>
    <div style="background:#fff; border:1px solid #dee2e6; border-radius:10px; padding:20px; text-align:center; margin:0 0 24px;">
      <p style="font-size:18px; font-weight:500; color:#1A3557; margin:0 0 20px;">How was your experience?</p>
      <div style="font-size:36px; margin:0 0 20px; letter-spacing:4px;">
        {''.join(f'<a href="{feedback_url}&rating={s}" style="text-decoration:none; color:#C9952A;">&#9733;</a>' for s in [1,2,3,4,5])}
      </div>
      <p style="font-size:12px; color:#5A6A7A; margin:0 0 16px;">Click a star — or click below to share more</p>
      <a href="{feedback_url}" style="background:#C9952A; color:#ffffff; padding:12px 28px; border-radius:9999px; text-decoration:none; font-size:14px; font-weight:500; display:inline-block;">
        Share your experience
      </a>
    </div>
    <p style="font-size:13px; color:#5A6A7A; line-height:1.6;">
      This link is for your booking only and expires in 30 days.
      If you have any questions or concerns, reply directly to this email or call us at (408) 831-2101.
    </p>
  </div>
  <div style="background:#1A3557; padding:14px; border-radius:0 0 8px 8px; text-align:center;">
    <p style="color:#F5C97A; margin:0; font-size:12px;">Bay Area Experiences &bull; (408) 831-2101 &bull; bayareaexperiences.com</p>
  </div>
</body>
</html>'''

        txt_body = (
            f'Hi {booking.guest_first_name},\n\n'
            f'Thank you for your {booking.experience.name} experience!\n\n'
            f'Share your feedback here: {feedback_url}\n\n'
            f'This link expires in 30 days.\n\n'
            f'Bay Area Experiences\n(408) 831-2101'
        )

        msg = Message(
            subject=subject,
            recipients=[token.email_sent_to],
            html=html_body,
            body=txt_body,
        )
        mail.send(msg)
        return True
    except Exception as e:
        import logging
        logging.getLogger('reviews').error(f'send_feedback_request failed: {e}')
        return False
