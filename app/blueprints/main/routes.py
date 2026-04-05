import os
from datetime import datetime, timezone
from flask import render_template, redirect, url_for, send_from_directory, current_app, request, jsonify, make_response
from sqlalchemy import func
from app.blueprints.main import main_bp
from app.models import Experience, ExperienceReview
from app.extensions import db


@main_bp.route('/images/<path:filename>')
def image(filename):
    img_dir = os.path.join(current_app.root_path, 'templates', 'images')
    return send_from_directory(img_dir, filename)


@main_bp.route('/audio/<path:filename>')
def audio(filename):
    audio_dir = os.path.join(current_app.root_path, 'templates', 'audio')
    return send_from_directory(audio_dir, filename)


def _group_by_category(experiences):
    grouped = {}
    for exp in experiences:
        grouped.setdefault(exp.category or 'Other', []).append(exp)
    return grouped


@main_bp.route('/')
def index():
    experiences = (Experience.query
                   .filter_by(is_active=True)
                   .order_by(Experience.sort_order)
                   .all())
    from app.weather.cities import SERVING_CITIES
    serving_cities = SERVING_CITIES if current_app.config.get('WEATHER_ENABLED', True) else []
    return render_template('main/index.html',
                           grouped_experiences=_group_by_category(experiences),
                           serving_cities=serving_cities)


@main_bp.route('/experiences')
def experiences():
    experiences = (Experience.query
                   .filter_by(is_active=True)
                   .order_by(Experience.sort_order)
                   .all())
    grouped = _group_by_category(experiences)
    try:
        from app.tracking.events import track_event
        track_event('experience_list_viewed', category='navigation')
    except Exception:
        pass
    return render_template('main/experiences.html', grouped_experiences=grouped)


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


@main_bp.route('/sitemap.xml')
def sitemap():
    from app.models import Provider
    base = request.host_url.rstrip('/')

    # Static pages: (path, changefreq, priority)
    static_urls = [
        ('/',             'weekly',  '1.0'),
        ('/experiences',  'weekly',  '0.9'),
        ('/contact',      'monthly', '0.6'),
        ('/login',        'monthly', '0.4'),
        ('/register',     'monthly', '0.5'),
        ('/join/provider','monthly', '0.5'),
    ]

    # Dynamic: active experiences
    experiences = (Experience.query
                   .filter_by(is_active=True)
                   .with_entities(Experience.slug, Experience.updated_at)
                   .all())

    # Dynamic: active provider public profiles (no updated_at on Provider model)
    providers = (Provider.query
                 .filter_by(is_active=True)
                 .with_entities(Provider.business_slug)
                 .all())

    xml = render_template('main/sitemap.xml',
                          base=base,
                          static_urls=static_urls,
                          experiences=experiences,
                          providers=providers,
                          now=datetime.now(timezone.utc).strftime('%Y-%m-%d'))
    resp = make_response(xml)
    resp.headers['Content-Type'] = 'application/xml; charset=utf-8'
    return resp


@main_bp.route('/robots.txt')
def robots():
    base = request.host_url.rstrip('/')
    txt = (
        'User-agent: *\n'
        'Disallow: /admin/\n'
        'Disallow: /account/\n'
        'Disallow: /checkout/\n'
        'Disallow: /cart/\n'
        'Disallow: /book/\n'
        'Disallow: /provider/dashboard/\n'
        'Disallow: /providers/onboarding/\n'
        f'Sitemap: {base}/sitemap.xml\n'
    )
    resp = make_response(txt)
    resp.headers['Content-Type'] = 'text/plain'
    return resp


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
