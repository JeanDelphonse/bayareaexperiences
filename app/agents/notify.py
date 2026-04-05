"""Admin notification when an agent run lands in the approval queue."""
import logging
from flask import current_app
from app.utils import send_email

log = logging.getLogger('agents')

AGENT_LABELS = {
    'BAE-AGENT-SOCIAL':   'Social Media Agent',
    'BAE-AGENT-ADS':      'Google Ads Agent',
    'BAE-AGENT-EMAIL':    'Email & Loyalty Agent',
    'BAE-AGENT-PARTNER':  'Partnership Agent',
    'BAE-AGENT-MYSTERY':  'Mystery Tour Agent',
}


def send_approval_needed_email(run):
    try:
        from app.extensions import mail as _mail
        admin_email = current_app.config.get('ADMIN_EMAIL', '')
        if not admin_email:
            return
        label = AGENT_LABELS.get(run.agent_code, run.agent_code)
        body_html = (
            f'<p>An agent draft is waiting for your approval.</p>'
            f'<p><strong>Agent:</strong> {label}<br>'
            f'<strong>Trigger:</strong> {run.trigger_type}'
            f'{" — " + run.trigger_detail if run.trigger_detail else ""}<br>'
            f'<strong>Run ID:</strong> {run.run_id}</p>'
            f'<p><a href="https://bayareaexperiences.com/admin/agents/queue">'
            f'Review in the approval queue →</a></p>'
        )
        send_email(
            _mail,
            subject=f'[BAE Agent] Approval needed — {label}',
            recipients=[admin_email],
            body_html=body_html,
        )
    except Exception as e:
        log.warning(f'send_approval_needed_email failed: {e}')
