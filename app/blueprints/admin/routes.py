import csv
import io
import threading
from datetime import date, time as dt_time, timedelta
from flask import (render_template, redirect, url_for, flash,
                   request, jsonify, Response, current_app)
from flask_login import login_required, current_user
from sqlalchemy import func
from app.blueprints.admin import admin_bp
from app.extensions import db
from app.models import (Experience, ExperiencePickupLocation, Timeslot,
                        Booking, StaffMember, User, ContactSubmission,
                        ChatSession, ChatMessage)
from app.utils import admin_required, generate_pk, paginate, send_email

PICKUP_CITIES = [
    'Cupertino, CA', 'Fremont, CA', 'Los Gatos, CA', 'Menlo Park, CA',
    'Monterey, CA', 'Mountain View, CA', 'Palo Alto, CA', 'Redwood City, CA',
    'San Francisco, CA', 'San Jose, CA', 'Santa Clara, CA', 'Santa Cruz, CA',
    'Sunnyvale, CA',
]


@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    total_bookings   = Booking.query.count()
    today_bookings   = Booking.query.join(Timeslot).filter(
        Timeslot.slot_date == date.today()).count()
    week_start       = date.today() - timedelta(days=date.today().weekday())
    week_bookings    = Booking.query.join(Timeslot).filter(
        Timeslot.slot_date >= week_start).count()
    total_revenue    = db.session.query(func.sum(Booking.amount_paid)).scalar() or 0
    recent_bookings  = (Booking.query.order_by(Booking.created_at.desc()).limit(10).all())
    null_staff_count = Booking.query.filter(
        Booking.staff_id == None,
        Booking.booking_status == 'confirmed').count()
    unread_contacts  = ContactSubmission.query.filter_by(is_read=False).count()
    from app.models import ExperienceReview
    held_reviews    = ExperienceReview.query.filter_by(status='held').count()
    flagged_reviews = ExperienceReview.query.filter_by(status='flagged').count()
    return render_template('admin/dashboard.html',
                           total_bookings=total_bookings,
                           today_bookings=today_bookings,
                           week_bookings=week_bookings,
                           total_revenue=total_revenue,
                           recent_bookings=recent_bookings,
                           null_staff_count=null_staff_count,
                           unread_contacts=unread_contacts,
                           held_reviews=held_reviews,
                           flagged_reviews=flagged_reviews)


# ── Experiences ────────────────────────────────────────────────────────────────

@admin_bp.route('/experiences', methods=['GET', 'POST'])
@login_required
@admin_required
def experiences():
    if request.method == 'POST':
        name          = request.form.get('name', '').strip()
        slug          = request.form.get('slug', '').strip()
        category      = request.form.get('category', '').strip()
        description   = request.form.get('description', '').strip()
        duration      = float(request.form.get('duration_hours', 0))
        price         = float(request.form.get('price', 0))
        deposit       = request.form.get('deposit_amount') or None
        payment_mode  = request.form.get('payment_mode', 'full')
        max_guests    = int(request.form.get('max_guests', 4))
        advance_days  = int(request.form.get('advance_booking_days', 1))
        allow_reschedule = request.form.get('allow_online_reschedule') == 'on'
        staff_id      = request.form.get('staff_id') or None
        is_active     = request.form.get('is_active') == 'on'
        photo_url     = request.form.get('photo_url', '').strip()
        pickup_cities = request.form.getlist('pickup_cities')

        exp = Experience(
            experience_id=generate_pk(),
            name=name, slug=slug, category=category,
            description=description, duration_hours=duration,
            price=price, deposit_amount=deposit,
            payment_mode=payment_mode, max_guests=max_guests,
            advance_booking_days=advance_days,
            allow_online_reschedule=allow_reschedule,
            staff_id=staff_id, is_active=is_active,
            photo_url=photo_url,
            sort_order=Experience.query.count() + 1,
            core_stops=request.form.get('core_stops', '').strip() or None,
        )
        db.session.add(exp)
        db.session.flush()

        for city in pickup_cities:
            db.session.add(ExperiencePickupLocation(
                id=generate_pk(), experience_id=exp.experience_id, pickup_city=city))

        db.session.commit()
        flash(f'Experience "{name}" created.', 'success')
        return redirect(url_for('admin.experiences'))

    all_exps  = paginate(Experience.query.order_by(Experience.sort_order))
    all_staff = StaffMember.query.filter_by(is_active=True).all()
    return render_template('admin/experiences.html',
                           experiences=all_exps, staff=all_staff,
                           pickup_cities=PICKUP_CITIES)


@admin_bp.route('/experiences/<experience_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_experience(experience_id):
    exp       = Experience.query.get_or_404(experience_id)
    all_staff = StaffMember.query.filter_by(is_active=True).all()
    existing_cities = [loc.pickup_city for loc in exp.pickup_locations]

    if request.method == 'POST':
        exp.name         = request.form.get('name', '').strip()
        exp.slug         = request.form.get('slug', '').strip()
        exp.category     = request.form.get('category', '').strip()
        exp.description  = request.form.get('description', '').strip()
        exp.duration_hours = float(request.form.get('duration_hours', 0))
        exp.price        = float(request.form.get('price', 0))
        deposit_val      = request.form.get('deposit_amount')
        exp.deposit_amount = float(deposit_val) if deposit_val else None
        exp.payment_mode = request.form.get('payment_mode', 'full')
        exp.max_guests   = int(request.form.get('max_guests', 4))
        exp.advance_booking_days = int(request.form.get('advance_booking_days', 1))
        exp.allow_online_reschedule = request.form.get('allow_online_reschedule') == 'on'
        exp.staff_id     = request.form.get('staff_id') or None
        exp.is_active    = request.form.get('is_active') == 'on'
        exp.photo_url    = request.form.get('photo_url', '').strip()
        exp.core_stops   = request.form.get('core_stops', '').strip() or None

        # Update pickup locations
        ExperiencePickupLocation.query.filter_by(experience_id=experience_id).delete()
        for city in request.form.getlist('pickup_cities'):
            db.session.add(ExperiencePickupLocation(
                id=generate_pk(), experience_id=experience_id, pickup_city=city))

        db.session.commit()
        flash('Experience updated.', 'success')
        return redirect(url_for('admin.experiences'))

    return render_template('admin/experience_form.html', experience=exp,
                           staff=all_staff, pickup_cities=PICKUP_CITIES,
                           existing_cities=existing_cities)


@admin_bp.route('/experiences/<experience_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_experience(experience_id):
    exp = Experience.query.get_or_404(experience_id)
    exp.is_active = False
    db.session.commit()
    flash(f'Experience "{exp.name}" deactivated.', 'info')
    return redirect(url_for('admin.experiences'))


@admin_bp.route('/experiences/reorder', methods=['POST'])
@login_required
@admin_required
def reorder_experiences():
    data = request.get_json(force=True)
    for item in data:
        exp = Experience.query.get(item['id'])
        if exp:
            exp.sort_order = item['order']
    db.session.commit()
    return jsonify({'status': 'ok'})


# ── Timeslots ──────────────────────────────────────────────────────────────────

@admin_bp.route('/timeslots', methods=['GET', 'POST'])
@login_required
@admin_required
def timeslots():
    if request.method == 'POST':
        experience_id = request.form.get('experience_id')
        slot_date     = date.fromisoformat(request.form.get('slot_date'))
        start_time    = dt_time.fromisoformat(request.form.get('start_time'))
        end_time      = dt_time.fromisoformat(request.form.get('end_time'))
        capacity      = int(request.form.get('capacity', 4))

        slot = Timeslot(
            timeslot_id=generate_pk(),
            experience_id=experience_id,
            slot_date=slot_date,
            start_time=start_time,
            end_time=end_time,
            capacity=capacity,
        )
        db.session.add(slot)
        db.session.commit()
        flash('Timeslot created.', 'success')
        return redirect(url_for('admin.timeslots'))

    all_exps  = Experience.query.filter_by(is_active=True).order_by(Experience.sort_order).all()
    slots_q   = (Timeslot.query
                 .join(Experience)
                 .order_by(Timeslot.slot_date.desc(), Timeslot.start_time))
    all_slots = paginate(slots_q)
    return render_template('admin/timeslots.html', experiences=all_exps, timeslots=all_slots)


@admin_bp.route('/timeslots/bulk', methods=['GET', 'POST'])
@login_required
@admin_required
def bulk_timeslots():
    if request.method == 'POST':
        experience_id = request.form.get('experience_id')
        start_date    = date.fromisoformat(request.form.get('start_date'))
        end_date      = date.fromisoformat(request.form.get('end_date'))
        repeat_days   = request.form.getlist('repeat_days')  # ['0','1',...,'6'] Mon-Sun
        start_time    = dt_time.fromisoformat(request.form.get('start_time'))
        end_time      = dt_time.fromisoformat(request.form.get('end_time'))
        capacity      = int(request.form.get('capacity', 4))

        created = 0
        current = start_date
        while current <= end_date:
            if not repeat_days or str(current.weekday()) in repeat_days:
                slot = Timeslot(
                    timeslot_id=generate_pk(),
                    experience_id=experience_id,
                    slot_date=current,
                    start_time=start_time,
                    end_time=end_time,
                    capacity=capacity,
                )
                db.session.add(slot)
                created += 1
            current += timedelta(days=1)

        db.session.commit()
        flash(f'{created} timeslots created.', 'success')
        return redirect(url_for('admin.timeslots'))

    all_exps = Experience.query.filter_by(is_active=True).order_by(Experience.sort_order).all()
    return render_template('admin/bulk_timeslots.html', experiences=all_exps)


# ── Bookings ───────────────────────────────────────────────────────────────────

@admin_bp.route('/bookings')
@login_required
@admin_required
def bookings():
    query = Booking.query

    # Filters
    exp_id   = request.args.get('experience_id')
    status   = request.args.get('status')
    date_from = request.args.get('date_from')
    date_to   = request.args.get('date_to')
    staff_id  = request.args.get('staff_id')

    if exp_id:
        query = query.filter(Booking.experience_id == exp_id)
    if status:
        query = query.filter(Booking.booking_status == status)
    if date_from:
        query = query.join(Timeslot).filter(Timeslot.slot_date >= date.fromisoformat(date_from))
    if date_to:
        if not date_from:
            query = query.join(Timeslot)
        query = query.filter(Timeslot.slot_date <= date.fromisoformat(date_to))
    if staff_id:
        query = query.filter(Booking.staff_id == staff_id)

    # CSV export
    if request.args.get('export') == 'csv':
        bkgs = query.all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['booking_id', 'experience', 'guest_name', 'guest_email',
                         'guest_count', 'date', 'pickup_city', 'amount_total',
                         'amount_paid', 'payment_status', 'booking_status', 'created_at'])
        for b in bkgs:
            writer.writerow([
                b.booking_id, b.experience.name,
                f'{b.guest_first_name} {b.guest_last_name}',
                b.guest_email, b.guest_count,
                b.timeslot.slot_date.isoformat(), b.pickup_city,
                b.amount_total, b.amount_paid,
                b.payment_status, b.booking_status,
                b.created_at.isoformat(),
            ])
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=bookings_export.csv'},
        )

    bkgs      = paginate(query.order_by(Booking.created_at.desc()))
    all_exps  = Experience.query.order_by(Experience.sort_order).all()
    all_staff = StaffMember.query.all()
    return render_template('admin/bookings.html',
                           bookings=bkgs, experiences=all_exps, staff=all_staff)


@admin_bp.route('/bookings/<booking_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def booking_detail(booking_id):
    import json
    from app.itinerary.storage import get_active_itinerary, get_all_itinerary_versions
    booking = Booking.query.get_or_404(booking_id)
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update_status':
            booking.booking_status = request.form.get('booking_status')
            db.session.commit()
            flash('Booking status updated.', 'success')
        elif action == 'update_notes':
            booking.notes = request.form.get('notes', '').strip()
            db.session.commit()
            flash('Notes saved.', 'success')
        return redirect(url_for('admin.booking_detail', booking_id=booking_id))
    itinerary_record = get_active_itinerary(booking_id)
    itinerary = None
    if itinerary_record:
        try:
            itinerary = json.loads(itinerary_record.itinerary_json)
        except (ValueError, TypeError):
            itinerary = None
    itinerary_versions = get_all_itinerary_versions(booking_id)
    all_staff = StaffMember.query.filter_by(is_active=True).order_by(StaffMember.full_name).all()
    assignment_logs = (booking.assignment_logs if hasattr(booking, 'assignment_logs') else [])
    return render_template(
        'admin/booking_detail.html',
        booking=booking,
        itinerary=itinerary,
        itinerary_record=itinerary_record,
        itinerary_versions=itinerary_versions,
        is_admin_view=True,
        all_staff=all_staff,
        assignment_logs=assignment_logs,
    )


# ── Admin: Assign BAE Staff to Booking (AJAX) ─────────────────────────────────

@admin_bp.route('/bookings/<booking_id>/assign-staff', methods=['POST'])
@login_required
@admin_required
def admin_assign_staff(booking_id):
    from app.models import StaffAssignmentLog
    booking = Booking.query.get_or_404(booking_id)
    data = request.get_json(silent=True) or {}
    staff_id = (data.get('staff_id') or '').strip() or None
    reason   = (data.get('reason')   or '').strip() or None

    member = None
    if staff_id:
        member = StaffMember.query.filter_by(staff_id=staff_id, is_active=True).first()
        if not member:
            return jsonify({'ok': False, 'error': 'Staff member not found'}), 400

    log = StaffAssignmentLog(
        log_id=generate_pk(),
        booking_id=booking_id,
        changed_by_user_id=current_user.user_id,
        changed_by_role='admin',
        previous_staff_id=booking.staff_id,
        new_staff_id=staff_id,
        reason=reason,
    )
    db.session.add(log)
    booking.staff_id = staff_id
    db.session.commit()

    if member and member.email:
        _notify_bae_staff_assigned(booking, member)

    staff_name = member.full_name if member else 'Unassigned'
    return jsonify({'ok': True, 'staff_name': staff_name})


@admin_bp.route('/staff/<staff_id>/send-invite', methods=['POST'])
@login_required
@admin_required
def admin_send_staff_invite(staff_id):
    from app.extensions import mail as _mail
    from app.staff.portal import send_staff_portal_invite
    member = StaffMember.query.get_or_404(staff_id)
    send_staff_portal_invite(member, _mail)
    flash(f'Portal invite sent to {member.email}.', 'success')
    return redirect(url_for('admin.staff'))


def _notify_bae_staff_assigned(booking, member):
    try:
        body_html = render_template(
            'staff/email_assignment_notification.html',
            booking=booking,
            staff_name=member.full_name,
        )
        _app   = current_app._get_current_object()
        _email = member.email
        _bid   = booking.booking_id
        from app.extensions import mail as _mail
        _m = _mail

        def _send():
            with _app.app_context():
                try:
                    send_email(
                        _m,
                        subject=f'New Assignment: {booking.experience.name} — {booking.timeslot.slot_date}',
                        recipients=[_email],
                        body_html=body_html,
                    )
                except Exception as e:
                    _app.logger.error(f'Staff assignment email failed for booking {_bid}: {e}')

        threading.Thread(target=_send, daemon=True).start()
    except Exception as e:
        current_app.logger.error(f'Failed to prepare staff assignment email: {e}')


# ── Staff ──────────────────────────────────────────────────────────────────────

@admin_bp.route('/staff', methods=['GET', 'POST'])
@login_required
@admin_required
def staff():
    if request.method == 'POST':
        member = StaffMember(
            staff_id=generate_pk(),
            full_name=request.form.get('full_name', '').strip(),
            title=request.form.get('title', '').strip(),
            phone=request.form.get('phone', '').strip(),
            email=request.form.get('email', '').strip().lower(),
            notes=request.form.get('notes', '').strip(),
            is_active=request.form.get('is_active') == 'on',
        )
        db.session.add(member)
        db.session.commit()
        flash('Staff member added.', 'success')
        return redirect(url_for('admin.staff'))

    all_staff = paginate(StaffMember.query.order_by(StaffMember.full_name))
    return render_template('admin/staff.html', staff=all_staff)


@admin_bp.route('/staff/<staff_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_staff(staff_id):
    member = StaffMember.query.get_or_404(staff_id)
    if request.method == 'POST':
        member.full_name = request.form.get('full_name', '').strip()
        member.title     = request.form.get('title', '').strip()
        member.phone     = request.form.get('phone', '').strip()
        member.email     = request.form.get('email', '').strip().lower()
        member.notes     = request.form.get('notes', '').strip()
        member.is_active = request.form.get('is_active') == 'on'
        db.session.commit()
        flash('Staff member updated.', 'success')
        return redirect(url_for('admin.staff'))
    return render_template('admin/staff_form.html', member=member)


# ── Contact Submissions ─────────────────────────────────────────────────────

@admin_bp.route('/contact-submissions')
@login_required
@admin_required
def contact_submissions():
    unread_filter = request.args.get('unread')
    subject_filter = request.args.get('subject')
    query = ContactSubmission.query
    if unread_filter:
        query = query.filter_by(is_read=False)
    if subject_filter:
        query = query.filter_by(subject=subject_filter)

    # CSV export
    if request.args.get('export') == 'csv':
        rows = query.order_by(ContactSubmission.created_at.desc()).all()
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(['submission_id', 'full_name', 'visitor_email', 'phone',
                    'subject', 'referral_source', 'email_sent', 'sms_sent',
                    'is_read', 'created_at'])
        for s in rows:
            w.writerow([s.submission_id, s.full_name, s.visitor_email, s.phone or '',
                        s.subject, s.referral_source or '', s.email_sent, s.sms_sent,
                        s.is_read, s.created_at.isoformat()])
        return Response(out.getvalue(), mimetype='text/csv',
                        headers={'Content-Disposition': 'attachment; filename=contact_submissions.csv'})

    submissions  = paginate(query.order_by(ContactSubmission.created_at.desc()))
    unread_count = ContactSubmission.query.filter_by(is_read=False).count()
    return render_template('admin/contact_submissions.html',
                           submissions=submissions, unread_count=unread_count)


@admin_bp.route('/contact-submissions/<submission_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def contact_submission_detail(submission_id):
    sub = ContactSubmission.query.get_or_404(submission_id)
    if not sub.is_read:
        sub.is_read = True
        db.session.commit()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'notes':
            sub.admin_notes = request.form.get('admin_notes', '').strip()
            db.session.commit()
            flash('Notes saved.', 'success')
        elif action == 'toggle_read':
            sub.is_read = not sub.is_read
            db.session.commit()
        return redirect(url_for('admin.contact_submission_detail', submission_id=submission_id))
    return render_template('admin/contact_submission_detail.html', sub=sub)


@admin_bp.route('/contact-submissions/<submission_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_contact_submission(submission_id):
    sub = ContactSubmission.query.get_or_404(submission_id)
    db.session.delete(sub)
    db.session.commit()
    flash('Submission deleted.', 'info')
    return redirect(url_for('admin.contact_submissions'))


# ── Chat Sessions ─────────────────────────────────────────────────────────────

@admin_bp.route('/chat-sessions')
@login_required
@admin_required
def chat_sessions():
    query = ChatSession.query
    if request.args.get('escalated'):
        query = query.filter_by(was_escalated=True)
    sessions  = paginate(query.order_by(ChatSession.started_at.desc()))
    today_count     = ChatSession.query.filter(
        func.date(ChatSession.started_at) == date.today()).count()
    escalated_count = ChatSession.query.filter_by(was_escalated=True).count()
    return render_template('admin/chat_sessions.html',
                           sessions=sessions, today_count=today_count,
                           escalated_count=escalated_count)


@admin_bp.route('/chat-sessions/<session_id>')
@login_required
@admin_required
def chat_session_detail(session_id):
    cs = ChatSession.query.get_or_404(session_id)
    messages = cs.messages.order_by(ChatMessage.created_at).all()
    return render_template('admin/chat_session_detail.html', cs=cs, messages=messages)


# ── Reviews ─────────────────────────────────────────────────────────────────────

@admin_bp.route('/reviews')
@login_required
@admin_required
def reviews():
    from app.models import ExperienceReview
    status = request.args.get('status')
    rating = request.args.get('rating', type=int)
    page   = request.args.get('page', 1, type=int)

    q = ExperienceReview.query
    if status:
        q = q.filter_by(status=status)
    if rating:
        q = q.filter_by(star_rating=rating)
    q = q.order_by(ExperienceReview.submitted_at.desc())
    pagination = q.paginate(page=page, per_page=25, error_out=False)
    return render_template('admin/reviews.html',
                           reviews=pagination.items,
                           pagination=pagination)


@admin_bp.route('/reviews/held')
@login_required
@admin_required
def reviews_held():
    from app.models import ExperienceReview
    reviews = ExperienceReview.query.filter_by(status='held').order_by(
        ExperienceReview.held_until.asc()).all()
    return render_template('admin/reviews_held.html', reviews=reviews)


@admin_bp.route('/reviews/flagged')
@login_required
@admin_required
def reviews_flagged():
    from app.models import ExperienceReview
    reviews = ExperienceReview.query.filter_by(status='flagged').order_by(
        ExperienceReview.submitted_at.desc()).all()
    return render_template('admin/reviews_flagged.html', reviews=reviews)


@admin_bp.route('/reviews/<review_id>')
@login_required
@admin_required
def review_detail(review_id):
    from app.models import ExperienceReview
    review = ExperienceReview.query.filter_by(review_id=review_id).first_or_404()
    return render_template('admin/review_detail.html', review=review)


@admin_bp.route('/reviews/<review_id>/publish', methods=['POST'])
@login_required
@admin_required
def review_publish(review_id):
    from app.models import ExperienceReview
    from datetime import datetime, timezone
    review = ExperienceReview.query.filter_by(review_id=review_id).first_or_404()
    review.status       = 'published'
    review.published_at = datetime.now(timezone.utc)
    review.held_until   = None
    _update_review_rating(review.experience_id)
    db.session.commit()
    flash('Review published.', 'success')
    return redirect(request.referrer or url_for('admin.reviews'))


@admin_bp.route('/reviews/<review_id>/flag', methods=['POST'])
@login_required
@admin_required
def review_flag_admin(review_id):
    from app.models import ExperienceReview
    review = ExperienceReview.query.filter_by(review_id=review_id).first_or_404()
    review.status = 'flagged'
    db.session.commit()
    flash('Review flagged.', 'warning')
    return redirect(request.referrer or url_for('admin.reviews'))


@admin_bp.route('/reviews/<review_id>/remove', methods=['POST'])
@login_required
@admin_required
def review_remove(review_id):
    from app.models import ExperienceReview
    review = ExperienceReview.query.filter_by(review_id=review_id).first_or_404()
    review.status = 'removed'
    _update_review_rating(review.experience_id)
    db.session.commit()
    flash('Review removed.', 'success')
    return redirect(request.referrer or url_for('admin.reviews'))


@admin_bp.route('/reviews/<review_id>/feature', methods=['POST'])
@login_required
@admin_required
def review_feature(review_id):
    from app.models import ExperienceReview
    review = ExperienceReview.query.filter_by(review_id=review_id).first_or_404()
    review.is_featured = not review.is_featured
    db.session.commit()
    flash('Review updated.', 'success')
    return redirect(request.referrer or url_for('admin.review_detail', review_id=review_id))


@admin_bp.route('/reviews/<review_id>/notes', methods=['POST'])
@login_required
@admin_required
def review_notes(review_id):
    from app.models import ExperienceReview
    review = ExperienceReview.query.filter_by(review_id=review_id).first_or_404()
    review.admin_notes = request.form.get('admin_notes', '').strip() or None
    db.session.commit()
    flash('Notes saved.', 'success')
    return redirect(url_for('admin.review_detail', review_id=review_id))


@admin_bp.route('/reviews/analytics')
@login_required
@admin_required
def reviews_analytics():
    from app.models import ExperienceReview, Experience
    total_published = ExperienceReview.query.filter_by(status='published').count()
    total_held      = ExperienceReview.query.filter_by(status='held').count()
    total_flagged   = ExperienceReview.query.filter_by(status='flagged').count()
    avg_result      = db.session.query(func.avg(ExperienceReview.star_rating)).filter_by(status='published').scalar()
    avg_rating      = float(avg_result) if avg_result else None

    rows = db.session.query(
        Experience.name,
        func.count(ExperienceReview.review_id).label('count'),
        func.avg(ExperienceReview.star_rating).label('avg'),
    ).join(ExperienceReview, Experience.experience_id == ExperienceReview.experience_id) \
     .filter(ExperienceReview.status == 'published') \
     .group_by(Experience.experience_id, Experience.name) \
     .order_by(func.count(ExperienceReview.review_id).desc()).all()

    per_experience = [{'name': r.name, 'count': r.count, 'avg': float(r.avg) if r.avg else None} for r in rows]
    return render_template('admin/reviews_analytics.html',
                           total_published=total_published,
                           total_held=total_held,
                           total_flagged=total_flagged,
                           avg_rating=avg_rating,
                           per_experience=per_experience)


@admin_bp.route('/reviews/export')
@login_required
@admin_required
def reviews_export():
    import csv, io
    from app.models import ExperienceReview
    reviews = ExperienceReview.query.filter_by(status='published').order_by(
        ExperienceReview.submitted_at.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['review_id', 'experience', 'star_rating', 'reviewer',
                     'best_moment', 'submitted_at', 'helpful_count'])
    for r in reviews:
        writer.writerow([r.review_id, r.experience.name, r.star_rating,
                         r.reviewer_display_name, r.best_moment,
                         r.submitted_at.strftime('%Y-%m-%d %H:%M'), r.helpful_count])
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment;filename=reviews_export.csv'})


@admin_bp.route('/reviews/publish-held', methods=['POST'])
@login_required
@admin_required
def publish_held_reviews():
    from app.reviews.scheduler import auto_publish_held_reviews
    count = auto_publish_held_reviews()
    flash(f'{count} held review(s) published.', 'success')
    return redirect(url_for('admin.reviews_held'))


def _update_review_rating(experience_id):
    from app.models import ExperienceReview, Experience
    result = db.session.query(
        func.avg(ExperienceReview.star_rating).label('avg'),
        func.count(ExperienceReview.review_id).label('cnt'),
    ).filter(
        ExperienceReview.experience_id == experience_id,
        ExperienceReview.status == 'published',
    ).one()
    db.session.query(Experience).filter_by(experience_id=experience_id).update({
        'avg_star_rating': round(float(result.avg), 2) if result.avg else None,
        'review_count':    result.cnt,
    })
