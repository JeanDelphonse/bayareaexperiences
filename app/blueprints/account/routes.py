from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.blueprints.account import account_bp
from app.extensions import db, bcrypt
from app.models import Booking

PICKUP_CITIES = [
    'Cupertino', 'Fremont', 'Los Gatos', 'Menlo Park',
    'Monterey', 'Mountain View', 'Palo Alto', 'Redwood City',
    'San Francisco', 'San Jose', 'Santa Clara',
    'Santa Cruz', 'Sunnyvale',
]


@account_bp.route('/dashboard')
@login_required
def dashboard():
    return redirect(url_for('account.bookings'))


@account_bp.route('/dashboard/bookings')
@login_required
def bookings():
    from app.models import UserPreferenceProfile
    user_bookings = (Booking.query
                     .filter_by(user_id=current_user.user_id)
                     .order_by(Booking.created_at.desc())
                     .all())
    user_pref_profile = UserPreferenceProfile.query.filter_by(
        user_id=current_user.user_id).first()
    return render_template('account/bookings.html',
                           bookings=user_bookings,
                           user_pref_profile=user_pref_profile)


@account_bp.route('/dashboard/bookings/<booking_id>')
@login_required
def booking_detail(booking_id):
    import json
    from app.itinerary.storage import get_active_itinerary
    booking = Booking.query.filter_by(
        booking_id=booking_id,
        user_id=current_user.user_id,
    ).first_or_404()
    itinerary_record = get_active_itinerary(booking_id)
    itinerary = None
    if itinerary_record:
        try:
            itinerary = json.loads(itinerary_record.itinerary_json)
        except (ValueError, TypeError):
            itinerary = None
    from datetime import date
    return render_template(
        'account/booking_detail.html',
        booking=booking,
        itinerary=itinerary,
        itinerary_version=itinerary_record.version if itinerary_record else None,
        itinerary_generated_at=itinerary_record.generated_at if itinerary_record else None,
        is_fallback=itinerary_record.is_fallback if itinerary_record else False,
        today=date.today(),
    )


@account_bp.route('/dashboard/profile', methods=['GET', 'POST'])
@login_required
def profile():
    from app.models import UserPreferenceProfile
    from app.preferences.engine import PERSONAS, INTEREST_TAG_GROUPS

    if request.method == 'POST':
        current_user.first_name = request.form.get('first_name', '').strip()
        current_user.last_name  = request.form.get('last_name', '').strip()
        current_user.phone      = request.form.get('phone', '').strip()
        current_user.address    = request.form.get('address', '').strip()
        current_user.city       = request.form.get('city', '').strip()
        current_user.state      = request.form.get('state', '').strip()
        current_user.postal_zip = request.form.get('postal_zip', '').strip()
        current_user.notes      = request.form.get('notes', '').strip()
        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('account.profile') + '?tab=details')

    active_tab        = request.args.get('tab', 'details')
    user_pref_profile = UserPreferenceProfile.query.filter_by(
        user_id=current_user.user_id).first()

    saved_persona_ids = set()
    saved_tags        = set()
    if user_pref_profile:
        if user_pref_profile.personas:
            saved_persona_ids = {p.strip() for p in user_pref_profile.personas.split(',') if p.strip()}
        if user_pref_profile.interest_tags:
            saved_tags = {t.strip() for t in user_pref_profile.interest_tags.split(',') if t.strip()}

    all_tags = [tag for group in INTEREST_TAG_GROUPS.values() for tag in group]

    return render_template('account/profile.html',
                           active_tab        = active_tab,
                           user_pref_profile = user_pref_profile,
                           saved_persona_ids = saved_persona_ids,
                           saved_tags        = saved_tags,
                           personas          = PERSONAS,
                           all_tags          = all_tags,
                           pickup_cities     = PICKUP_CITIES)


@account_bp.route('/dashboard/profile/preferences', methods=['POST'])
@login_required
def save_preference_profile():
    """Save or update the user's persistent preference profile."""
    from app.models import UserPreferenceProfile
    from app.preferences.engine import PERSONAS

    personas_raw  = request.form.get('personas', '').strip()
    tags_raw      = request.form.get('interest_tags', '').strip()
    notes         = request.form.get('preference_notes', '')[:500].strip()
    pickup_city   = request.form.get('default_pickup_city', '').strip() or None
    accessibility = request.form.get('accessibility_needs', '')[:500].strip() or None
    dietary       = request.form.get('dietary_preferences', '')[:300].strip() or None
    marketing     = request.form.get('marketing_opt_in') == 'on'

    valid_ids = {p['id'] for p in PERSONAS}
    personas  = [p.strip() for p in personas_raw.split(',') if p.strip() in valid_ids][:3]
    tags      = [t.strip() for t in tags_raw.split(',') if t.strip()]
    labels    = ', '.join([
        next((p['label'] for p in PERSONAS if p['id'] == pid), pid)
        for pid in personas
    ])

    _upsert_preference_profile(
        user_id             = current_user.user_id,
        personas            = ','.join(personas),
        persona_labels      = labels,
        interest_tags       = ','.join(tags),
        notes               = notes,
        default_pickup_city = pickup_city,
        accessibility_needs = accessibility,
        dietary_preferences = dietary,
        marketing_opt_in    = marketing,
        source              = 'profile_page',
    )

    flash('Your travel preferences have been saved.', 'success')
    return redirect(url_for('account.profile') + '?tab=preferences')


@account_bp.route('/dashboard/profile/preferences/clear', methods=['POST'])
@login_required
def clear_preference_profile():
    """Delete the user's saved preference profile."""
    from app.models import UserPreferenceProfile
    profile = UserPreferenceProfile.query.filter_by(
        user_id=current_user.user_id).first()
    if profile:
        db.session.delete(profile)
        db.session.commit()
    flash('Your travel preferences have been cleared.', 'success')
    return redirect(url_for('account.profile') + '?tab=preferences')


@account_bp.route('/dashboard/password', methods=['POST'])
@login_required
def change_password():
    current_pw = request.form.get('current_password', '')
    new_pw     = request.form.get('new_password', '')
    confirm    = request.form.get('confirm_password', '')
    if not bcrypt.check_password_hash(current_user.password_hash, current_pw):
        flash('Current password is incorrect.', 'danger')
    elif new_pw != confirm or len(new_pw) < 8:
        flash('New passwords must match and be at least 8 characters.', 'danger')
    else:
        current_user.password_hash = bcrypt.generate_password_hash(new_pw, rounds=12).decode('utf-8')
        db.session.commit()
        flash('Password changed successfully.', 'success')
    return redirect(url_for('account.profile'))


def _upsert_preference_profile(user_id, personas, persona_labels=None,
                                interest_tags='', notes='',
                                default_pickup_city=None, accessibility_needs=None,
                                dietary_preferences=None, marketing_opt_in=True,
                                source='profile_page'):
    """Shared helper — create or update UserPreferenceProfile. Never raises."""
    try:
        from app.models import UserPreferenceProfile
        from app.preferences.engine import PERSONAS as _PERSONAS
        from datetime import datetime, timezone
        from app.utils import generate_pk

        if persona_labels is None:
            valid = {p['id'] for p in _PERSONAS}
            pids  = [p.strip() for p in personas.split(',') if p.strip() in valid][:3]
            persona_labels = ', '.join([
                next((p['label'] for p in _PERSONAS if p['id'] == pid), pid)
                for pid in pids
            ])

        now     = datetime.now(timezone.utc)
        profile = UserPreferenceProfile.query.filter_by(user_id=user_id).first()
        if profile:
            profile.personas            = personas or None
            profile.persona_labels      = persona_labels or None
            profile.interest_tags       = interest_tags or None
            profile.preference_notes    = notes or None
            if default_pickup_city is not None:
                profile.default_pickup_city = default_pickup_city or None
            if accessibility_needs is not None:
                profile.accessibility_needs = accessibility_needs
            if dietary_preferences is not None:
                profile.dietary_preferences = dietary_preferences
            profile.marketing_opt_in    = marketing_opt_in
            profile.preference_source   = source
            profile.updated_at          = now
        else:
            profile = UserPreferenceProfile(
                profile_id          = generate_pk(),
                user_id             = user_id,
                personas            = personas or None,
                persona_labels      = persona_labels or None,
                interest_tags       = interest_tags or None,
                preference_notes    = notes or None,
                default_pickup_city = default_pickup_city or None,
                accessibility_needs = accessibility_needs,
                dietary_preferences = dietary_preferences,
                marketing_opt_in    = marketing_opt_in,
                preference_source   = source,
                created_at          = now,
                updated_at          = now,
            )
            db.session.add(profile)
        db.session.commit()
    except Exception as e:
        import logging
        logging.getLogger('account').error(f'_upsert_preference_profile failed for {user_id}: {e}')
