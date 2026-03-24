"""Nightly aggregation job — computes daily_stats, experience_stats, utm_campaigns.

Run via cPanel Cron Jobs at 2:00 AM UTC:
  0 2 * * *  cd /home/user/bayareaexperiences && python -c \
    "from app import create_app; from app.tracking.aggregator import run_daily_aggregation; \
     app=create_app('production'); ctx=app.app_context(); ctx.push(); run_daily_aggregation()"

Also performs raw-event cleanup (>TRACKING_RETENTION_DAYS old).
"""
import json
from datetime import date, datetime, timezone, timedelta
from sqlalchemy import func, cast, Date


def run_daily_aggregation(target_date: date = None):
    """Aggregate raw tracking data for target_date (default: yesterday). Idempotent."""
    from app.models import (SiteSession, PageView, UserEvent,
                             DailyStat, ExperienceStat, UtmCampaign,
                             FunnelStep, Booking, Experience)
    from app.extensions import db
    from app.utils import generate_pk

    if target_date is None:
        target_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()

    # ── Site-wide daily stats ────────────────────────────────────────────────
    sessions = SiteSession.query.filter(
        cast(SiteSession.started_at, Date) == target_date).all()

    total_sessions  = len(sessions)
    unique_visitors = len(set(s.ip_hash for s in sessions if s.ip_hash))
    bounced         = sum(1 for s in sessions if s.is_bounce)
    bounce_rate     = round(bounced / total_sessions * 100, 2) if total_sessions else 0
    durations       = [s.duration_seconds for s in sessions if s.duration_seconds]
    avg_duration    = int(sum(durations) / len(durations)) if durations else 0

    total_pv = PageView.query.filter(
        cast(PageView.viewed_at, Date) == target_date).count()

    # Device & referrer breakdowns
    device_counts, ref_counts = {}, {}
    for s in sessions:
        k = s.device_type or 'unknown'
        device_counts[k] = device_counts.get(k, 0) + 1
        r = s.referrer_type or 'unknown'
        ref_counts[r]    = ref_counts.get(r, 0) + 1

    # Bookings from authoritative bookings table
    bookings_today = Booking.query.filter(
        cast(Booking.created_at, Date) == target_date,
        Booking.booking_status == 'confirmed').all()
    revenue_today  = sum(float(b.amount_total) for b in bookings_today)

    # Funnel counts
    funnel = {}
    for step in ('experience_view', 'booking_start', 'timeslot_select',
                 'cart_add', 'checkout_start', 'payment_attempt', 'booking_complete'):
        funnel[step] = FunnelStep.query.filter(
            cast(FunnelStep.entered_at, Date) == target_date,
            FunnelStep.step_name == step).count()

    # Top pages
    top_pages_q = (db.session.query(PageView.url_path, func.count().label('cnt'))
                   .filter(cast(PageView.viewed_at, Date) == target_date)
                   .group_by(PageView.url_path)
                   .order_by(func.count().desc())
                   .limit(10).all())
    top_pages = [{'path': r.url_path, 'views': r.cnt} for r in top_pages_q]

    # New accounts
    from app.models import User
    new_accounts = User.query.filter(
        cast(User.created_at, Date) == target_date).count()

    # Contact submissions
    from app.models import ContactSubmission
    contact_subs = ContactSubmission.query.filter(
        cast(ContactSubmission.created_at, Date) == target_date).count()

    # Chat sessions started
    from app.models import ChatSession as CS
    chat_starts = CS.query.filter(
        cast(CS.started_at, Date) == target_date).count()

    # 404 / 500 counts from user_events
    err_404 = UserEvent.query.filter(
        cast(UserEvent.occurred_at, Date) == target_date,
        UserEvent.event_type == 'page_not_found').count()
    err_500 = UserEvent.query.filter(
        cast(UserEvent.occurred_at, Date) == target_date,
        UserEvent.event_type == 'server_error').count()

    # Upsert DailyStat
    stat = DailyStat.query.filter_by(stat_date=target_date).first()
    if not stat:
        stat = DailyStat(stat_id=generate_pk(), stat_date=target_date)
        db.session.add(stat)

    stat.total_sessions       = total_sessions
    stat.total_page_views     = total_pv
    stat.unique_visitors      = unique_visitors
    stat.bounce_rate          = bounce_rate
    stat.avg_session_duration = avg_duration
    stat.device_breakdown     = json.dumps(device_counts)
    stat.referrer_breakdown   = json.dumps(ref_counts)
    stat.booking_funnel       = json.dumps(funnel)
    stat.top_pages            = json.dumps(top_pages)
    stat.bookings_completed   = len(bookings_today)
    stat.revenue_total        = revenue_today
    stat.new_accounts         = new_accounts
    stat.contact_submissions  = contact_subs
    stat.chat_sessions_started= chat_starts
    stat.error_404_count      = err_404
    stat.error_500_count      = err_500
    stat.computed_at          = datetime.now(timezone.utc)
    db.session.commit()
    print(f'Daily stats aggregated for {target_date}')

    # ── Experience stats ─────────────────────────────────────────────────────
    experiences = Experience.query.filter_by(is_active=True).all()
    for exp in experiences:
        views = UserEvent.query.filter(
            cast(UserEvent.occurred_at, Date) == target_date,
            UserEvent.event_type == 'experience_viewed',
            UserEvent.target_id == exp.experience_id).count()
        starts = UserEvent.query.filter(
            cast(UserEvent.occurred_at, Date) == target_date,
            UserEvent.event_type == 'booking_started',
            UserEvent.target_id == exp.experience_id).count()
        completed = Booking.query.filter(
            cast(Booking.created_at, Date) == target_date,
            Booking.booking_status == 'confirmed',
            Booking.experience_id == exp.experience_id).count()
        rev = db.session.query(func.sum(Booking.amount_total)).filter(
            cast(Booking.created_at, Date) == target_date,
            Booking.booking_status == 'confirmed',
            Booking.experience_id == exp.experience_id).scalar() or 0
        cart_adds = UserEvent.query.filter(
            cast(UserEvent.occurred_at, Date) == target_date,
            UserEvent.event_type == 'cart_item_added',
            UserEvent.target_id == exp.experience_id).count()
        conversion = round(completed / views * 100, 2) if views else None
        abandonment = None
        if starts:
            abandoned = UserEvent.query.filter(
                cast(UserEvent.occurred_at, Date) == target_date,
                UserEvent.event_type == 'booking_abandoned',
                UserEvent.target_id == exp.experience_id).count()
            abandonment = round(abandoned / starts * 100, 2)

        es = ExperienceStat.query.filter_by(
            experience_id=exp.experience_id, stat_date=target_date).first()
        if not es:
            es = ExperienceStat(stat_id=generate_pk(),
                                experience_id=exp.experience_id,
                                stat_date=target_date)
            db.session.add(es)
        es.views              = views
        es.booking_starts     = starts
        es.bookings_completed = completed
        es.conversion_rate    = conversion
        es.revenue            = float(rev)
        es.cart_adds          = cart_adds
        es.abandonment_rate   = abandonment
    db.session.commit()
    print(f'Experience stats aggregated for {target_date}')

    # ── UTM campaigns ────────────────────────────────────────────────────────
    utm_sessions = SiteSession.query.filter(
        cast(SiteSession.started_at, Date) == target_date,
        SiteSession.utm_source != None).all()

    utm_groups = {}
    for s in utm_sessions:
        key = (s.utm_source or '', s.utm_medium or '', s.utm_campaign or '')
        if key not in utm_groups:
            utm_groups[key] = {'sessions': 0, 'page_views': 0, 'bounced': 0, 'duration': []}
        g = utm_groups[key]
        g['sessions'] += 1
        g['page_views'] += s.page_count or 0
        if s.is_bounce:
            g['bounced'] += 1
        if s.duration_seconds:
            g['duration'].append(s.duration_seconds)

    for (src, med, cam), data in utm_groups.items():
        bkgs = Booking.query.join(SiteSession,
                                   Booking.user_id == SiteSession.user_id).filter(
            cast(Booking.created_at, Date) == target_date,
            SiteSession.utm_source == src,
            SiteSession.utm_campaign == cam).count() if src else 0
        rev = 0

        uc = UtmCampaign.query.filter_by(
            utm_source=src, utm_medium=med, utm_campaign=cam,
            stat_date=target_date).first()
        if not uc:
            uc = UtmCampaign(campaign_id=generate_pk(),
                              utm_source=src, utm_medium=med,
                              utm_campaign=cam, stat_date=target_date)
            db.session.add(uc)
        n = data['sessions']
        uc.sessions             = n
        uc.page_views           = data['page_views']
        uc.bookings_completed   = bkgs
        uc.revenue              = rev
        uc.bounce_rate          = round(data['bounced'] / n * 100, 2) if n else None
        uc.avg_session_duration = int(sum(data['duration']) / len(data['duration'])) if data['duration'] else None
    db.session.commit()
    print(f'UTM campaigns aggregated for {target_date}')

    # ── Cleanup old events ───────────────────────────────────────────────────
    cleanup_old_events()


def cleanup_old_events(retention_days: int = 90):
    """Delete raw tracking rows older than retention_days."""
    from app.models import PageView, UserEvent, SiteSession, FunnelStep
    from app.extensions import db
    from datetime import datetime, timezone, timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    PageView.query.filter(PageView.viewed_at < cutoff).delete()
    UserEvent.query.filter(UserEvent.occurred_at < cutoff).delete()
    FunnelStep.query.filter(FunnelStep.entered_at < cutoff).delete()
    SiteSession.query.filter(SiteSession.started_at < cutoff).delete()
    db.session.commit()
    print(f'Cleaned up tracking events older than {cutoff.date()}')
