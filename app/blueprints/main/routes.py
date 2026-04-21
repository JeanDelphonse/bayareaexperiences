import json
import os
import random
from datetime import datetime, timezone, date, timedelta
from flask import render_template, redirect, url_for, send_from_directory, current_app, request, jsonify, make_response
from sqlalchemy import func
from app.blueprints.main import main_bp
from app.models import Experience, ExperienceReview, Timeslot
from app.extensions import db


@main_bp.route('/images/<path:filename>')
def image(filename):
    img_dir = os.path.join(current_app.root_path, 'templates', 'images')
    return send_from_directory(img_dir, filename)


@main_bp.route('/audio/<path:filename>')
def audio(filename):
    audio_dir = os.path.join(current_app.root_path, 'templates', 'audio')
    return send_from_directory(audio_dir, filename)


def _get_featured_experiences():
    """Return up to 3 randomly selected active experiences that have at least
    one available timeslot within the next 7 days, with badge + slot data."""
    today    = date.today()
    week_end = today + timedelta(days=7)

    # IDs of experiences with ≥1 open slot this week
    available_ids = [
        row[0] for row in
        db.session.query(Timeslot.experience_id)
        .filter(
            Timeslot.slot_date > today,
            Timeslot.slot_date <= week_end,
            Timeslot.is_available == True,
            Timeslot.booked_count < Timeslot.capacity,
        )
        .distinct()
        .all()
    ]

    if not available_ids:
        return []

    candidates = (
        Experience.query
        .filter(
            Experience.experience_id.in_(available_ids),
            Experience.is_active == True,
            Experience.is_mystery == False,
        )
        .all()
    )

    selected = random.sample(candidates, min(3, len(candidates)))

    result = []
    for exp in selected:
        slots = (
            Timeslot.query
            .filter(
                Timeslot.experience_id == exp.experience_id,
                Timeslot.slot_date > today,
                Timeslot.slot_date <= week_end,
                Timeslot.is_available == True,
                Timeslot.booked_count < Timeslot.capacity,
            )
            .order_by(Timeslot.slot_date, Timeslot.start_time)
            .limit(3)
            .all()
        )

        slot_count = (
            Timeslot.query
            .filter(
                Timeslot.experience_id == exp.experience_id,
                Timeslot.slot_date > today,
                Timeslot.slot_date <= week_end,
                Timeslot.is_available == True,
                Timeslot.booked_count < Timeslot.capacity,
            )
            .count()
        )

        if slot_count == 1:
            badge_class, badge_text = 'slots-low', 'Filling fast'
        elif slot_count <= 3:
            badge_class, badge_text = 'slots-medium', 'A few spots left'
        else:
            badge_class, badge_text = 'slots-good', 'Spots available'

        result.append({
            'experience': exp,
            'slots':      slots,
            'badge_class': badge_class,
            'badge_text':  badge_text,
        })

    return result


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
                           serving_cities=serving_cities,
                           featured=_get_featured_experiences())


@main_bp.route('/experiences/featured')
def featured_experiences():
    featured = _get_featured_experiences()
    fmt = request.args.get('format', 'json')

    if fmt == 'html':
        return render_template('partials/_featured_experiences.html', featured=featured)

    data = []
    for item in featured:
        exp = item['experience']
        data.append({
            'experience_id':   exp.experience_id,
            'name':            exp.name,
            'slug':            exp.slug,
            'category':        exp.category,
            'description':     exp.description,
            'duration_hours':  float(exp.duration_hours),
            'price':           float(exp.price),
            'effective_price': float(exp.effective_price),
            'is_discount_live': exp.is_discount_live,
            'discount_percent': exp.discount_percent,
            'discount_label':  exp.discount_label,
            'photo_url':       exp.photo_url or '',
            'badge_class':     item['badge_class'],
            'badge_text':      item['badge_text'],
            'slots': [
                {
                    'timeslot_id': s.timeslot_id,
                    'slot_date':   s.slot_date.strftime('%Y-%m-%d'),
                    'start_time':  s.start_time.strftime('%H:%M'),
                }
                for s in item['slots']
            ],
        })
    return jsonify(data)


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

    # ── Sample itinerary (BAE-PRD-SAMPLE-ITINERARY-v1.0) ─────────────────────
    sample_itinerary  = None
    sample_generating = False
    if exp.sample_itinerary:
        try:
            sample_itinerary = json.loads(exp.sample_itinerary)
        except (json.JSONDecodeError, TypeError):
            sample_itinerary = None
    else:
        from app.itinerary.sample import generate_and_store_async
        generate_and_store_async(current_app._get_current_object(),
                                 exp.experience_id)
        sample_generating = True

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

    related_experiences = (
        Experience.query
        .filter(
            Experience.is_active     == True,
            Experience.is_mystery    == False,
            Experience.experience_id != exp.experience_id,
        )
        .order_by(Experience.sort_order.asc())
        .all()
    )

    return render_template('main/experience_detail.html',
                           experience=exp,
                           reviews=reviews,
                           star_counts=star_counts,
                           has_more_reviews=has_more_reviews,
                           min_reviews=min_reviews,
                           sample_itinerary=sample_itinerary,
                           sample_generating=sample_generating,
                           related_experiences=related_experiences)


@main_bp.route('/sitemap.xml')
def sitemap():
    from app.models import Provider
    base = request.host_url.rstrip('/')

    # Static pages: (path, changefreq, priority)
    static_urls = [
        ('/',                  'weekly',  '1.0'),
        ('/experiences',       'weekly',  '0.9'),
        ('/contact',           'monthly', '0.6'),
        ('/providers/apply',   'monthly', '0.5'),
        ('/register',          'monthly', '0.5'),
        ('/login',             'monthly', '0.4'),
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


@main_bp.route('/llms.txt')
def llms_txt():
    content = """\
# Bay Area Experiences

> Bay Area Experiences is a premium private-tour and transportation company serving the San Francisco Bay Area, California. Every experience is fully private (your group only), door-to-door, and conducted in a signature Jeep Wrangler. Maximum 4 guests per booking. Pickup available from 13 cities across the Bay Area.

## About

Bay Area Experiences offers curated small-group guided tours, scenic drives, hiking adventures, wine country trips, tech campus tours, and private on-demand transport. All bookings are flat-rate (not per-person) and include complimentary refreshments on board. Expert local guides lead every tour. Online booking with secure Stripe checkout; full payment collected at time of booking.

## Core Experiences

- [SF City Icons & Hidden Gems](https://www.bayareaexperiences.com/experience/sf-city-icons): 5-hour private tour — Painted Ladies, Fisherman's Wharf, Mission murals, hidden staircases locals love. $465 flat, up to 4 guests.
- [Coastal Charm & Scenic Drive](https://www.bayareaexperiences.com/experience/coastal-charm): 10-hour California coastal road trip — Big Sur cliffs, Carmel-by-the-Sea, wild Pacific coast. $825 flat.
- [Wine Country & Redwood Giants](https://www.bayareaexperiences.com/experience/wine-country-redwoods): 8-hour journey — Napa/Sonoma wine tasting combined with ancient coastal redwood groves. $705 flat.
- [Hiking Adventures & Bay Views](https://www.bayareaexperiences.com/experience/hiking-bay-views): 6-hour guided hike tailored to fitness level — Marin Headlands, Mt. Tamalpais, or Point Reyes. $585 flat.
- [Silicon Valley Innovation Trail](https://www.bayareaexperiences.com/experience/silicon-valley-trail): 6-hour tech campus tour — Apple Park, Googleplex, Meta HQ, Stanford University. $525 flat.
- [East Bay Vibe — Arts, Views & Eats](https://www.bayareaexperiences.com/experience/east-bay-vibe): 7-hour East Bay tour — Oakland arts scene, Rockridge dining, Berkeley, Grizzly Peak views. $625 flat.
- [Private Transport — Up to 3 Hours](https://www.bayareaexperiences.com/experience/transport-3hr): Door-to-door Jeep transport anywhere within a 3-hour round trip — airports, events, day trips. $195 flat.
- [Private Transport — Up to 6 Hours](https://www.bayareaexperiences.com/experience/transport-6hr): Extended private transport, up to 6-hour round trip. Up to 4 guests. $375 flat.

## Pricing Model

All prices are flat-rate per booking, not per person. A group of 1 and a group of 4 pay the same price. Complimentary power snacks and water are included on all tours. No hidden fees.

## Pickup Cities (13 Bay Area locations)

Cupertino, Fremont, Los Gatos, Menlo Park, Monterey, Mountain View, Palo Alto, Redwood City, San Francisco, San Jose, Santa Clara, Santa Cruz, Sunnyvale.

Guests select their pickup city at checkout. The guide arrives at the guest's specified door.

## Booking

- [Browse experiences](https://www.bayareaexperiences.com/experiences): Full catalog of tours and transport options.
- [Book an experience](https://www.bayareaexperiences.com/book): Select experience → pick a date → choose pickup city → guest count → Stripe checkout.
- Advance notice: 1 day minimum for most tours; 2 days for full-day trips (Yosemite, Monterey).
- Group size: 1–4 guests. Each booking is always private — no strangers added to your group.
- Payment: Stripe (all major credit and debit cards). Full amount charged at booking.

## Provider Marketplace

Third-party local guides ("providers") can apply to list their own experiences on Bay Area Experiences.

- [Become a provider](https://www.bayareaexperiences.com/join/provider): Landing page with incentive details.
- [Provider application](https://www.bayareaexperiences.com/providers/apply): Submit an application (account required).
- Free tier: up to 3 active experience listings. Pro tier (paid): unlimited listings.
- Providers earn 80% of booking revenue (20% platform commission). High-volume providers (10+ bookings/month for 3 consecutive months) earn a reduced 12% commission rate.
- Referral program: providers earn $100 credit for each new provider they refer who reaches 5 confirmed bookings.

## Customer Reviews

Verified reviews are collected after each completed booking and displayed on individual experience pages. Reviews go through a moderation workflow before publication.

## Key Pages

- [Home](https://www.bayareaexperiences.com/): Overview of all experience categories.
- [All Experiences](https://www.bayareaexperiences.com/experiences): Full tour and transport catalog.
- [Contact](https://www.bayareaexperiences.com/contact): Contact form for inquiries.
- [Register](https://www.bayareaexperiences.com/register): Create a customer account.
- [Login](https://www.bayareaexperiences.com/login): Sign in to manage bookings and account.

## Business Details

- Service area: San Francisco Bay Area, California, USA
- Vehicle: Signature Jeep Wrangler (all experiences)
- Group privacy: Every booking is fully private — only your party
- Maximum guests: 4 per booking
- Included on all tours: complimentary power snacks and water
- Payment processor: Stripe
- Languages: English
"""
    resp = make_response(content)
    resp.headers['Content-Type'] = 'text/plain; charset=utf-8'
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
