"""Admin analytics views — /admin/analytics/* """
import csv
import io
import json
from datetime import date, timedelta, datetime, timezone
from flask import render_template, request, redirect, url_for, Response
from flask_login import login_required
from sqlalchemy import func, cast, Date
from app.blueprints.admin import admin_bp
from app.extensions import db
from app.utils import admin_required


def _date_range():
    """Return (start, end) from ?start=&end= query params, default last 30 days."""
    today = date.today()
    try:
        end   = date.fromisoformat(request.args.get('end',   today.isoformat()))
        start = date.fromisoformat(request.args.get('start', (today - timedelta(days=29)).isoformat()))
    except ValueError:
        end   = today
        start = today - timedelta(days=29)
    return start, end


def _daily_stats_range(start, end):
    from app.models import DailyStat
    return DailyStat.query.filter(
        DailyStat.stat_date >= start,
        DailyStat.stat_date <= end
    ).order_by(DailyStat.stat_date).all()


# ── Overview ─────────────────────────────────────────────────────────────────

@admin_bp.route('/analytics')
@login_required
@admin_required
def analytics_overview():
    from app.models import DailyStat
    start, end = _date_range()
    stats = _daily_stats_range(start, end)

    total_sessions  = sum(s.total_sessions      or 0 for s in stats)
    unique_visitors = sum(s.unique_visitors      or 0 for s in stats)
    total_pv        = sum(s.total_page_views     or 0 for s in stats)
    total_revenue   = sum(float(s.revenue_total  or 0) for s in stats)
    total_bookings  = sum(s.bookings_completed   or 0 for s in stats)
    avg_bounce      = (sum(float(s.bounce_rate or 0) for s in stats) / len(stats)) if stats else 0
    avg_duration    = (sum(s.avg_session_duration or 0 for s in stats) / len(stats)) if stats else 0

    # Chart data — sessions per day
    chart_labels  = [s.stat_date.strftime('%b %d') for s in stats]
    chart_sessions = [s.total_sessions or 0 for s in stats]
    chart_revenue  = [float(s.revenue_total or 0) for s in stats]

    return render_template('admin/analytics/overview.html',
                           start=start, end=end,
                           total_sessions=total_sessions,
                           unique_visitors=unique_visitors,
                           total_page_views=total_pv,
                           total_revenue=total_revenue,
                           total_bookings=total_bookings,
                           avg_bounce_rate=round(avg_bounce, 1),
                           avg_duration=int(avg_duration),
                           chart_labels=json.dumps(chart_labels),
                           chart_sessions=json.dumps(chart_sessions),
                           chart_revenue=json.dumps(chart_revenue))


# ── Traffic ───────────────────────────────────────────────────────────────────

@admin_bp.route('/analytics/traffic')
@login_required
@admin_required
def analytics_traffic():
    start, end = _date_range()
    stats = _daily_stats_range(start, end)

    # Aggregate device & referrer breakdowns
    device_totals, ref_totals, top_pages_agg = {}, {}, {}
    for s in stats:
        for k, v in (json.loads(s.device_breakdown   or '{}') or {}).items():
            device_totals[k] = device_totals.get(k, 0) + v
        for k, v in (json.loads(s.referrer_breakdown  or '{}') or {}).items():
            ref_totals[k]    = ref_totals.get(k, 0)    + v
        for p in (json.loads(s.top_pages or '[]') or []):
            path = p.get('path', '')
            top_pages_agg[path] = top_pages_agg.get(path, 0) + p.get('views', 0)

    top_pages = sorted(top_pages_agg.items(), key=lambda x: x[1], reverse=True)[:10]

    return render_template('admin/analytics/traffic.html',
                           start=start, end=end,
                           device_totals=device_totals,
                           ref_totals=ref_totals,
                           top_pages=top_pages,
                           chart_device_labels=json.dumps(list(device_totals.keys())),
                           chart_device_data=json.dumps(list(device_totals.values())),
                           chart_ref_labels=json.dumps(list(ref_totals.keys())),
                           chart_ref_data=json.dumps(list(ref_totals.values())))


# ── Experiences ───────────────────────────────────────────────────────────────

@admin_bp.route('/analytics/experiences')
@login_required
@admin_required
def analytics_experiences():
    from app.models import ExperienceStat, Experience
    from sqlalchemy import func
    start, end = _date_range()

    rows = (db.session.query(
                Experience.name,
                func.sum(ExperienceStat.views).label('views'),
                func.sum(ExperienceStat.booking_starts).label('starts'),
                func.sum(ExperienceStat.bookings_completed).label('completed'),
                func.sum(ExperienceStat.revenue).label('revenue'),
                func.avg(ExperienceStat.conversion_rate).label('conversion'),
                func.avg(ExperienceStat.abandonment_rate).label('abandonment'),
            )
            .join(Experience, ExperienceStat.experience_id == Experience.experience_id)
            .filter(ExperienceStat.stat_date >= start, ExperienceStat.stat_date <= end)
            .group_by(Experience.experience_id, Experience.name)
            .order_by(func.sum(ExperienceStat.revenue).desc())
            .all())

    return render_template('admin/analytics/experiences.html',
                           start=start, end=end, rows=rows)


# ── Funnel ────────────────────────────────────────────────────────────────────

@admin_bp.route('/analytics/funnel')
@login_required
@admin_required
def analytics_funnel():
    start, end = _date_range()
    stats = _daily_stats_range(start, end)

    STEPS = ['experience_view', 'booking_start', 'timeslot_select',
             'cart_add', 'checkout_start', 'payment_attempt', 'booking_complete']
    LABELS = ['Experience View', 'Booking Start', 'Timeslot Select',
              'Cart Add', 'Checkout Start', 'Payment Attempt', 'Booking Complete']

    totals = {step: 0 for step in STEPS}
    for s in stats:
        funnel = json.loads(s.booking_funnel or '{}') or {}
        for step in STEPS:
            totals[step] += funnel.get(step, 0)

    funnel_data = [(LABELS[i], totals[step]) for i, step in enumerate(STEPS)]
    top = totals[STEPS[0]] or 1
    funnel_pct  = [(lbl, cnt, round(cnt / top * 100, 1)) for lbl, cnt in funnel_data]

    return render_template('admin/analytics/funnel.html',
                           start=start, end=end,
                           funnel_pct=funnel_pct,
                           chart_labels=json.dumps(LABELS),
                           chart_data=json.dumps([totals[s] for s in STEPS]))


# ── Users ─────────────────────────────────────────────────────────────────────

@admin_bp.route('/analytics/users')
@login_required
@admin_required
def analytics_users():
    start, end = _date_range()
    stats = _daily_stats_range(start, end)

    new_accounts   = sum(s.new_accounts       or 0 for s in stats)
    contact_subs   = sum(s.contact_submissions or 0 for s in stats)
    chat_starts    = sum(s.chat_sessions_started or 0 for s in stats)

    chart_labels      = [s.stat_date.strftime('%b %d') for s in stats]
    chart_new_users   = [s.new_accounts or 0 for s in stats]

    return render_template('admin/analytics/users.html',
                           start=start, end=end,
                           new_accounts=new_accounts,
                           contact_subs=contact_subs,
                           chat_starts=chat_starts,
                           chart_labels=json.dumps(chart_labels),
                           chart_new_users=json.dumps(chart_new_users))


# ── Campaigns ─────────────────────────────────────────────────────────────────

@admin_bp.route('/analytics/campaigns')
@login_required
@admin_required
def analytics_campaigns():
    from app.models import UtmCampaign
    from sqlalchemy import func
    start, end = _date_range()

    rows = (db.session.query(
                UtmCampaign.utm_source,
                UtmCampaign.utm_medium,
                UtmCampaign.utm_campaign,
                func.sum(UtmCampaign.sessions).label('sessions'),
                func.sum(UtmCampaign.page_views).label('page_views'),
                func.sum(UtmCampaign.bookings_completed).label('bookings'),
                func.sum(UtmCampaign.revenue).label('revenue'),
                func.avg(UtmCampaign.bounce_rate).label('bounce_rate'),
            )
            .filter(UtmCampaign.stat_date >= start, UtmCampaign.stat_date <= end)
            .group_by(UtmCampaign.utm_source,
                      UtmCampaign.utm_medium,
                      UtmCampaign.utm_campaign)
            .order_by(func.sum(UtmCampaign.sessions).desc())
            .all())

    return render_template('admin/analytics/campaigns.html',
                           start=start, end=end, rows=rows)


# ── Errors ────────────────────────────────────────────────────────────────────

@admin_bp.route('/analytics/errors')
@login_required
@admin_required
def analytics_errors():
    start, end = _date_range()
    stats = _daily_stats_range(start, end)

    total_404 = sum(s.error_404_count or 0 for s in stats)
    total_500 = sum(s.error_500_count or 0 for s in stats)

    chart_labels = [s.stat_date.strftime('%b %d') for s in stats]
    chart_404    = [s.error_404_count or 0 for s in stats]
    chart_500    = [s.error_500_count or 0 for s in stats]

    return render_template('admin/analytics/errors.html',
                           start=start, end=end,
                           total_404=total_404, total_500=total_500,
                           chart_labels=json.dumps(chart_labels),
                           chart_404=json.dumps(chart_404),
                           chart_500=json.dumps(chart_500))


# ── Export ────────────────────────────────────────────────────────────────────

@admin_bp.route('/analytics/export')
@login_required
@admin_required
def analytics_export():
    start, end = _date_range()
    stats = _daily_stats_range(start, end)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'date', 'sessions', 'unique_visitors', 'page_views',
        'bounce_rate', 'avg_duration_sec', 'bookings', 'revenue',
        'new_accounts', 'contact_submissions', 'chat_sessions',
        'errors_404', 'errors_500',
    ])
    for s in stats:
        writer.writerow([
            s.stat_date, s.total_sessions, s.unique_visitors, s.total_page_views,
            s.bounce_rate, s.avg_session_duration, s.bookings_completed,
            s.revenue_total, s.new_accounts, s.contact_submissions,
            s.chat_sessions_started, s.error_404_count, s.error_500_count,
        ])

    output.seek(0)
    filename = f'bae_analytics_{start}_{end}.csv'
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )
