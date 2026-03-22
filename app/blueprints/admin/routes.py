import csv
import io
from datetime import date, time as dt_time, timedelta
from flask import (render_template, redirect, url_for, flash,
                   request, jsonify, Response)
from flask_login import login_required
from sqlalchemy import func
from app.blueprints.admin import admin_bp
from app.extensions import db
from app.models import (Experience, ExperiencePickupLocation, Timeslot,
                        Booking, StaffMember, User, ContactSubmission,
                        ChatSession, ChatMessage)
from app.utils import admin_required, generate_pk

PICKUP_CITIES = ['San Francisco, CA', 'San Jose, CA', 'Santa Cruz, CA', 'Monterey, CA']


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
    return render_template('admin/dashboard.html',
                           total_bookings=total_bookings,
                           today_bookings=today_bookings,
                           week_bookings=week_bookings,
                           total_revenue=total_revenue,
                           recent_bookings=recent_bookings,
                           null_staff_count=null_staff_count,
                           unread_contacts=unread_contacts)


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
        )
        db.session.add(exp)
        db.session.flush()

        for city in pickup_cities:
            db.session.add(ExperiencePickupLocation(
                id=generate_pk(), experience_id=exp.experience_id, pickup_city=city))

        db.session.commit()
        flash(f'Experience "{name}" created.', 'success')
        return redirect(url_for('admin.experiences'))

    all_exps  = Experience.query.order_by(Experience.sort_order).all()
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
    all_slots = (Timeslot.query
                 .join(Experience)
                 .order_by(Timeslot.slot_date.desc(), Timeslot.start_time)
                 .all())
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

    page     = request.args.get('page', 1, type=int)
    bkgs     = query.order_by(Booking.created_at.desc()).paginate(page=page, per_page=25)
    all_exps = Experience.query.order_by(Experience.sort_order).all()
    all_staff = StaffMember.query.all()
    return render_template('admin/bookings.html',
                           bookings=bkgs, experiences=all_exps, staff=all_staff)


@admin_bp.route('/bookings/<booking_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def booking_detail(booking_id):
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
    return render_template('admin/booking_detail.html', booking=booking)


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

    all_staff = StaffMember.query.order_by(StaffMember.full_name).all()
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
    page          = request.args.get('page', 1, type=int)
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

    submissions  = query.order_by(ContactSubmission.created_at.desc()).paginate(page=page, per_page=25)
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
    page  = request.args.get('page', 1, type=int)
    query = ChatSession.query
    if request.args.get('escalated'):
        query = query.filter_by(was_escalated=True)
    sessions  = query.order_by(ChatSession.started_at.desc()).paginate(page=page, per_page=25)
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
