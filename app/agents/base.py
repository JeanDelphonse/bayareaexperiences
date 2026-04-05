"""Shared BaseAgent class — all 5 agents inherit from this."""
import json
import logging
import os
from datetime import datetime, timezone

log = logging.getLogger('agents')


def _get_client():
    import anthropic
    return anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY', ''))


class BaseAgent:
    code        = ''
    model       = 'claude-sonnet-4-6'
    max_tokens  = 1024
    temperature = 0.7

    # ── Setting helpers ───────────────────────────────────────────────────────

    def get_setting(self, key: str, default=None):
        """Read a persisted AgentSetting for this agent."""
        from app.models import AgentSetting
        row = AgentSetting.query.filter_by(agent_code=self.code, key=key).first()
        if row is None:
            return default
        try:
            return json.loads(row.value)
        except (ValueError, TypeError):
            return row.value

    def is_enabled(self) -> bool:
        env_key = self.code.replace('-', '_') + '_ENABLED'
        env_val = os.environ.get(env_key, 'True')
        return env_val.lower() not in ('false', '0', 'no')

    def is_test_mode(self) -> bool:
        return bool(self.get_setting('test_mode', False))

    # ── Main entry point ──────────────────────────────────────────────────────

    def run(self, trigger_type: str = 'manual', trigger_detail: str = None,
            context: dict = None):
        """Execute the agent, persist a run record, and return it."""
        from app.models import AgentRun
        from app.extensions import db
        from app.utils import generate_pk

        run = AgentRun(
            run_id         = generate_pk(),
            agent_code     = self.code,
            trigger_type   = trigger_type,
            trigger_detail = trigger_detail,
            input_context  = json.dumps(context or {}),
            status         = 'running',
            created_at     = datetime.now(timezone.utc),
        )
        db.session.add(run)
        db.session.commit()

        try:
            output = self.execute(context or {}, run)

            if self.is_test_mode():
                # Test mode: store draft but never publish or send
                run.output_draft = json.dumps(output)
                run.status       = 'pending_approval'
            elif self.requires_approval(output):
                run.output_draft = json.dumps(output)
                run.status       = 'pending_approval'
            else:
                run.output_draft = json.dumps(output)
                run.status       = 'approved'
                self.publish(output, run)
                run.status       = 'published'
                run.published_at = datetime.now(timezone.utc)

        except Exception as e:
            run.status      = 'failed'
            run.admin_notes = str(e)
            log.error(f'{self.code} run {run.run_id} failed: {e}', exc_info=True)

        run.completed_at = datetime.now(timezone.utc)
        db.session.commit()

        if run.status == 'pending_approval':
            self._notify_admin(run)

        return run

    # ── Overridden by subclasses ──────────────────────────────────────────────

    def execute(self, context: dict, run) -> dict:
        raise NotImplementedError

    def requires_approval(self, output: dict) -> bool:
        return True

    def publish(self, output: dict, run):
        pass

    # ── Claude helper ─────────────────────────────────────────────────────────

    def claude(self, system: str, user: str) -> str:
        client = _get_client()
        msg = client.messages.create(
            model      = self.model,
            max_tokens = self.max_tokens,
            temperature= self.temperature,
            system     = system,
            messages   = [{'role': 'user', 'content': user}],
        )
        return msg.content[0].text.strip()

    def _notify_admin(self, run):
        try:
            from app.agents.notify import send_approval_needed_email
            send_approval_needed_email(run)
        except Exception as e:
            log.warning(f'Admin notification failed for run {run.run_id}: {e}')
