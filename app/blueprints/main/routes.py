import os
from flask import render_template, redirect, url_for, send_from_directory, current_app, request, jsonify
from sqlalchemy import func
from app.blueprints.main import main_bp
from app.models import Experience, ExperienceReview
from app.extensions import db


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

    min_reviews = int(os.environ.get('MIN_REVIEWS_TO_DISPLAY', 3))
    reviews = ExperienceReview.query.filter_by(
        experience_id=exp.experience_id,
        status='published',
    ).order_by(
        ExperienceReview.is_featured.desc(),
        ExperienceReview.published_at.desc(),
    ).limit(10).all()

    has_more_reviews = ExperienceReview.query.filter_by(
        experience_id=exp.experience_id,
        status='published',
    ).count() > 10

    star_counts = {i: 0 for i in range(1, 6)}
    rows = db.session.query(
        ExperienceReview.star_rating,
        func.count(ExperienceReview.review_id),
    ).filter_by(
        experience_id=exp.experience_id,
        status='published',
    ).group_by(ExperienceReview.star_rating).all()
    for rating, count in rows:
        star_counts[rating] = count

    return render_template('main/experience_detail.html',
                           experience=exp,
                           reviews=reviews,
                           star_counts=star_counts,
                           has_more_reviews=has_more_reviews,
                           min_reviews=min_reviews)


@main_bp.route('/experience/<slug>/reviews')
def experience_reviews(slug):
    exp  = Experience.query.filter_by(slug=slug).first_or_404()
    page = request.args.get('page', 2, type=int)
    pagination = ExperienceReview.query.filter_by(
        experience_id=exp.experience_id,
        status='published',
    ).order_by(
        ExperienceReview.is_featured.desc(),
        ExperienceReview.published_at.desc(),
    ).paginate(page=page, per_page=10, error_out=False)
    return render_template('reviews/_review_cards.html',
                           reviews=pagination.items,
                           has_more=pagination.has_next,
                           slug=slug,
                           page=page)
