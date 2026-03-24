import json
from datetime import datetime, timezone
from flask import (request, Response, jsonify, session, current_app,
                   stream_with_context)
from flask_login import current_user
from app.blueprints.chat import chat_bp
from app.extensions import db, limiter
from app.models import ChatSession, ChatMessage
from app.utils import generate_pk
from app.chatbot.context import build_system_prompt
from app.chatbot.intent import classify_intent
from app.chatbot.guard import is_safe


def _get_or_create_session():
    """Return the current ChatSession, creating one if needed."""
    sid = session.get('chat_session_id')
    chat_session = ChatSession.query.get(sid) if sid else None

    if not chat_session:
        chat_session = ChatSession(
            session_id=generate_pk(),
            user_id=current_user.user_id if current_user.is_authenticated else None,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string[:500] if request.user_agent.string else None,
        )
        db.session.add(chat_session)
        db.session.commit()
        session['chat_session_id'] = chat_session.session_id

    return chat_session


@chat_bp.route('/stream', methods=['POST'])
@limiter.limit("20 per hour")
def stream():
    if not current_app.config.get('CHAT_ENABLED', True):
        return jsonify({'error': 'Chat is temporarily unavailable. Please use the contact form or call (408) 831-2101.'}), 503

    api_key = current_app.config.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return jsonify({'error': 'Chat is temporarily unavailable. Please use the contact form or call (408) 831-2101.'}), 503

    data = request.get_json(silent=True) or {}
    user_message = (data.get('message') or '').strip()[:500]

    if not user_message:
        return jsonify({'error': 'Empty message.'}), 400

    if not is_safe(user_message):
        return jsonify({'error': 'Your message could not be processed. Please rephrase your question.'}), 400

    intent = classify_intent(user_message)
    chat_session = _get_or_create_session()

    # Save user message
    user_msg = ChatMessage(
        message_id=generate_pk(),
        session_id=chat_session.session_id,
        role='user',
        content=user_message,
        intent=intent,
    )
    db.session.add(user_msg)
    chat_session.message_count += 1
    chat_session.last_active_at = datetime.now(timezone.utc)
    db.session.commit()

    try:
        from app.tracking.events import track_event
        track_event('chat_message_sent', category='engagement',
                    target_id=chat_session.session_id, target_type='chat_session')
    except Exception:
        pass

    # Build conversation history (rolling 10-pair window = 20 messages)
    history_limit = current_app.config.get('CHAT_HISTORY_LIMIT', 10) * 2
    past = (ChatMessage.query
            .filter_by(session_id=chat_session.session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(history_limit + 1)
            .all())
    past.reverse()
    # Exclude the message we just saved (last one)
    messages = [{'role': m.role, 'content': m.content} for m in past[:-1]]
    messages.append({'role': 'user', 'content': user_message})

    system_prompt = build_system_prompt(current_user if current_user.is_authenticated else None)
    max_tokens = current_app.config.get('CHAT_MAX_TOKENS', 1024)

    # Keep a reference for the generator closure
    app = current_app._get_current_object()
    session_id = chat_session.session_id

    def generate():
        import anthropic
        full_response = []
        tokens_used = None
        try:
            client = anthropic.Anthropic(api_key=api_key)
            with client.messages.stream(
                model='claude-sonnet-4-6',
                max_tokens=max_tokens,
                temperature=0.3,
                system=system_prompt,
                messages=messages,
            ) as stream_obj:
                for text_chunk in stream_obj.text_stream:
                    full_response.append(text_chunk)
                    yield f"data: {json.dumps({'text': text_chunk})}\n\n"
                final = stream_obj.get_final_message()
                if final and final.usage:
                    tokens_used = final.usage.output_tokens
        except Exception as exc:
            app.logger.error(f'Chat stream error: {exc}')
            yield f"data: {json.dumps({'error': 'Sorry, I encountered an error. Please try again or call (408) 831-2101.'})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

        # Persist assistant reply
        if full_response:
            with app.app_context():
                bot_msg = ChatMessage(
                    message_id=generate_pk(),
                    session_id=session_id,
                    role='assistant',
                    content=''.join(full_response),
                    tokens_used=tokens_used,
                )
                db.session.add(bot_msg)
                cs = ChatSession.query.get(session_id)
                if cs:
                    cs.message_count += 1
                    cs.last_active_at = datetime.now(timezone.utc)
                db.session.commit()

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        },
    )


@chat_bp.route('/history', methods=['GET'])
def history():
    sid = session.get('chat_session_id')
    if not sid:
        return jsonify({'messages': []})
    msgs = (ChatMessage.query
            .filter_by(session_id=sid)
            .order_by(ChatMessage.created_at)
            .all())
    return jsonify({'messages': [{'role': m.role, 'content': m.content} for m in msgs]})


@chat_bp.route('/escalate', methods=['POST'])
def escalate():
    sid = session.get('chat_session_id')
    if sid:
        cs = ChatSession.query.get(sid)
        if cs:
            cs.was_escalated = True
            cs.escalated_to_form = True
            db.session.commit()
            try:
                from app.tracking.events import track_event
                track_event('chat_escalated', category='engagement',
                            target_id=sid, target_type='chat_session')
            except Exception:
                pass
    return jsonify({'status': 'ok'})
