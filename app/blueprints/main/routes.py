import os
from flask import render_template, redirect, url_for, send_from_directory, current_app
from app.blueprints.main import main_bp
from app.models import Experience


@main_bp.route('/images/<path:filename>')
def image(filename):
    img_dir = os.path.join(current_app.root_path, 'templates', 'images')
    return send_from_directory(img_dir, filename)


@main_bp.route('/')
def index():
    experiences = (Experience.query
                   .filter_by(is_active=True)
                   .order_by(Experience.sort_order)
                   .all())
    return render_template('main/index.html', experiences=experiences)


@main_bp.route('/experiences')
def experiences():
    experiences = (Experience.query
                   .filter_by(is_active=True)
                   .order_by(Experience.sort_order)
                   .all())
    try:
        from app.tracking.events import track_event
        track_event('experience_list_viewed', category='navigation')
    except Exception:
        pass
    return render_template('main/experiences.html', experiences=experiences)


@main_bp.route('/ride')
def ride_redirect():
    return redirect(url_for('main.experiences'), 301)


@main_bp.route('/experience/<slug>')
def experience_detail(slug):
    exp = Experience.query.filter_by(slug=slug, is_active=True).first_or_404()
    try:
        from app.tracking.events import track_event
        track_event('experience_viewed', category='experience',
                    target_id=exp.experience_id, target_type='experience')
    except Exception:
        pass
    return render_template('main/experience_detail.html', experience=exp)
