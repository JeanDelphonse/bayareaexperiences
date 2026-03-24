from datetime import datetime, timezone
from flask_login import UserMixin
from app.extensions import db, login_manager
from app.utils import generate_pk


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)


# ── Users ─────────────────────────────────────────────────────────────────────

class User(db.Model, UserMixin):
    __tablename__ = 'users'

    user_id        = db.Column(db.String(9),   primary_key=True, default=generate_pk)
    first_name     = db.Column(db.String(80),  nullable=False)
    last_name      = db.Column(db.String(80),  nullable=False)
    email          = db.Column(db.String(150), unique=True, nullable=False)
    password_hash  = db.Column(db.String(255), nullable=False)
    phone          = db.Column(db.String(30))
    address        = db.Column(db.String(200))
    city           = db.Column(db.String(100))
    state          = db.Column(db.String(50))
    postal_zip     = db.Column(db.String(20))
    notes          = db.Column(db.Text)
    is_admin       = db.Column(db.Boolean, default=False)
    email_verified = db.Column(db.Boolean, default=False)
    created_at     = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at     = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                               onupdate=lambda: datetime.now(timezone.utc))

    # Flask-Login requires get_id() to return the PK
    def get_id(self):
        return self.user_id

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    bookings   = db.relationship('Booking',  backref='user', lazy='dynamic')
    cart_items = db.relationship('CartItem', backref='user', lazy='dynamic')


# ── Staff Members ──────────────────────────────────────────────────────────────

class StaffMember(db.Model):
    __tablename__ = 'staff_members'

    staff_id   = db.Column(db.String(9),   primary_key=True, default=generate_pk)
    full_name  = db.Column(db.String(150), nullable=False)
    title      = db.Column(db.String(100))
    phone      = db.Column(db.String(30))
    email      = db.Column(db.String(150), unique=True, nullable=False)
    notes      = db.Column(db.Text)
    is_active  = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


# ── Experiences ────────────────────────────────────────────────────────────────

class Experience(db.Model):
    __tablename__ = 'experiences'

    experience_id          = db.Column(db.String(9),   primary_key=True, default=generate_pk)
    name                   = db.Column(db.String(200), nullable=False)
    slug                   = db.Column(db.String(200), unique=True, nullable=False)
    category               = db.Column(db.String(100))
    description            = db.Column(db.Text)
    duration_hours         = db.Column(db.Numeric(4, 1), nullable=False)
    price                  = db.Column(db.Numeric(10, 2), nullable=False)
    deposit_amount         = db.Column(db.Numeric(10, 2))
    payment_mode           = db.Column(db.Enum('full', 'deposit', 'offline'), nullable=False, default='full')
    max_guests             = db.Column(db.Integer, default=4)
    advance_booking_days   = db.Column(db.Integer, default=1)
    allow_online_reschedule = db.Column(db.Boolean, default=False)
    staff_id               = db.Column(db.String(9), db.ForeignKey('staff_members.staff_id'))
    is_active              = db.Column(db.Boolean, default=True)
    photo_url              = db.Column(db.String(500))
    sort_order             = db.Column(db.Integer, default=0)
    created_at             = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at             = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                                       onupdate=lambda: datetime.now(timezone.utc))

    staff        = db.relationship('StaffMember', backref='experiences')
    timeslots    = db.relationship('Timeslot', backref='experience', lazy='dynamic')
    pickup_locations = db.relationship('ExperiencePickupLocation', backref='experience',
                                        cascade='all, delete-orphan')

    __table_args__ = (
        db.Index('ix_experiences_slug', 'slug'),
        db.Index('ix_experiences_sort_order', 'sort_order'),
    )


# ── Experience Pickup Locations ────────────────────────────────────────────────

class ExperiencePickupLocation(db.Model):
    __tablename__ = 'experience_pickup_locations'

    id            = db.Column(db.String(9),   primary_key=True, default=generate_pk)
    experience_id = db.Column(db.String(9),   db.ForeignKey('experiences.experience_id'), nullable=False)
    pickup_city   = db.Column(db.String(100), nullable=False)


# ── Timeslots ──────────────────────────────────────────────────────────────────

class Timeslot(db.Model):
    __tablename__ = 'timeslots'

    timeslot_id   = db.Column(db.String(9),  primary_key=True, default=generate_pk)
    experience_id = db.Column(db.String(9),  db.ForeignKey('experiences.experience_id'), nullable=False)
    slot_date     = db.Column(db.Date,       nullable=False)
    start_time    = db.Column(db.Time,       nullable=False)
    end_time      = db.Column(db.Time,       nullable=False)
    capacity      = db.Column(db.Integer,    default=4)
    booked_count  = db.Column(db.Integer,    default=0)
    is_available  = db.Column(db.Boolean,    default=True)

    __table_args__ = (
        db.Index('ix_timeslots_slot_date', 'slot_date'),
        db.Index('ix_timeslots_experience_id', 'experience_id'),
    )

    @property
    def remaining_capacity(self):
        return self.capacity - self.booked_count

    @property
    def is_fully_booked(self):
        return self.booked_count >= self.capacity


# ── Bookings ──────────────────────────────────────────────────────────────────

class Booking(db.Model):
    __tablename__ = 'bookings'

    booking_id      = db.Column(db.String(9),   primary_key=True, default=generate_pk)
    user_id         = db.Column(db.String(9),   db.ForeignKey('users.user_id'), nullable=True)
    experience_id   = db.Column(db.String(9),   db.ForeignKey('experiences.experience_id'), nullable=False)
    timeslot_id     = db.Column(db.String(9),   db.ForeignKey('timeslots.timeslot_id'), nullable=False)
    staff_id        = db.Column(db.String(9),   db.ForeignKey('staff_members.staff_id'), nullable=True)

    guest_first_name  = db.Column(db.String(80),  nullable=False)
    guest_last_name   = db.Column(db.String(80),  nullable=False)
    guest_email       = db.Column(db.String(150), nullable=False)
    guest_phone       = db.Column(db.String(30))
    guest_count       = db.Column(db.Integer,     nullable=False)
    pickup_city       = db.Column(db.String(100), nullable=False)
    pickup_address    = db.Column(db.String(200))
    special_requests  = db.Column(db.Text)

    payment_mode    = db.Column(db.Enum('full', 'deposit', 'offline'), nullable=False)
    amount_total    = db.Column(db.Numeric(10, 2), nullable=False)
    amount_paid     = db.Column(db.Numeric(10, 2), default=0.00)
    amount_due      = db.Column(db.Numeric(10, 2), default=0.00)
    payment_status  = db.Column(db.Enum('pending', 'partial', 'paid', 'offline'), nullable=False, default='pending')
    booking_status  = db.Column(db.Enum('confirmed', 'cancelled', 'rescheduled', 'completed'),
                                nullable=False, default='confirmed')
    notes           = db.Column(db.Text)
    stripe_payment_intent_id = db.Column(db.String(200))
    referral_source = db.Column(db.String(100))  # C1: hotel partner program tracking

    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    experience = db.relationship('Experience', backref='bookings')
    timeslot   = db.relationship('Timeslot',   backref='bookings')
    staff      = db.relationship('StaffMember', backref='bookings')

    __table_args__ = (
        db.Index('ix_bookings_booking_status', 'booking_status'),
        db.Index('ix_bookings_user_id', 'user_id'),
        db.Index('ix_bookings_experience_id', 'experience_id'),
    )


# ── Cart Items ─────────────────────────────────────────────────────────────────

class CartItem(db.Model):
    __tablename__ = 'cart_items'

    cart_item_id  = db.Column(db.String(9),   primary_key=True, default=generate_pk)
    user_id       = db.Column(db.String(9),   db.ForeignKey('users.user_id'), nullable=False)
    experience_id = db.Column(db.String(9),   db.ForeignKey('experiences.experience_id'), nullable=False)
    timeslot_id   = db.Column(db.String(9),   db.ForeignKey('timeslots.timeslot_id'), nullable=False)
    guest_count   = db.Column(db.Integer,     nullable=False)
    pickup_city   = db.Column(db.String(100), nullable=False)
    pickup_address = db.Column(db.String(200))
    added_at      = db.Column(db.DateTime,    nullable=False, default=lambda: datetime.now(timezone.utc))

    experience = db.relationship('Experience')
    timeslot   = db.relationship('Timeslot')


# ── Contact Submissions ────────────────────────────────────────────────────────

class ContactSubmission(db.Model):
    __tablename__ = 'contact_submissions'

    submission_id  = db.Column(db.String(9),   primary_key=True, default=generate_pk)
    full_name      = db.Column(db.String(150), nullable=False)
    visitor_email  = db.Column(db.String(150), nullable=False)
    phone          = db.Column(db.String(30))
    subject        = db.Column(db.String(100), nullable=False)
    message        = db.Column(db.Text,        nullable=False)
    referral_source = db.Column(db.String(100))
    ip_address     = db.Column(db.String(45))
    user_agent     = db.Column(db.String(500))
    email_sent     = db.Column(db.Boolean, default=False)
    sms_sent       = db.Column(db.Boolean, default=False)
    is_read        = db.Column(db.Boolean, default=False)
    admin_notes    = db.Column(db.Text)
    created_at     = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.Index('ix_contact_submissions_is_read', 'is_read'),
        db.Index('ix_contact_submissions_created_at', 'created_at'),
    )


# ── Chat Sessions ──────────────────────────────────────────────────────────────

class ChatSession(db.Model):
    __tablename__ = 'chat_sessions'

    session_id      = db.Column(db.String(9),   primary_key=True, default=generate_pk)
    user_id         = db.Column(db.String(9),   db.ForeignKey('users.user_id'), nullable=True)
    ip_address      = db.Column(db.String(45))
    user_agent      = db.Column(db.String(500))
    started_at      = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    last_active_at  = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                                onupdate=lambda: datetime.now(timezone.utc))
    message_count   = db.Column(db.Integer, default=0)
    was_escalated   = db.Column(db.Boolean, default=False)
    escalated_to_form = db.Column(db.Boolean, default=False)

    user     = db.relationship('User', backref='chat_sessions')
    messages = db.relationship('ChatMessage', backref='session', lazy='dynamic',
                               order_by='ChatMessage.created_at')

    __table_args__ = (
        db.Index('ix_chat_sessions_user_id', 'user_id'),
        db.Index('ix_chat_sessions_started_at', 'started_at'),
    )


# ── Chat Messages ─────────────────────────────────────────────────────────────

class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'

    message_id  = db.Column(db.String(9),  primary_key=True, default=generate_pk)
    session_id  = db.Column(db.String(9),  db.ForeignKey('chat_sessions.session_id'), nullable=False)
    role        = db.Column(db.Enum('user', 'assistant'), nullable=False)
    content     = db.Column(db.Text, nullable=False)
    intent      = db.Column(db.String(50))
    tokens_used = db.Column(db.Integer)
    created_at  = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.Index('ix_chat_messages_session_id', 'session_id'),
    )


# ── Analytics: Site Sessions ──────────────────────────────────────────────────

class SiteSession(db.Model):
    __tablename__ = 'site_sessions'

    session_id       = db.Column(db.String(9),   primary_key=True, default=generate_pk)
    user_id          = db.Column(db.String(9),   db.ForeignKey('users.user_id'), nullable=True)
    started_at       = db.Column(db.DateTime,    nullable=False, default=lambda: datetime.now(timezone.utc))
    last_seen_at     = db.Column(db.DateTime,    nullable=False, default=lambda: datetime.now(timezone.utc))
    ended_at         = db.Column(db.DateTime,    nullable=True)
    duration_seconds = db.Column(db.Integer,     nullable=True)
    page_count       = db.Column(db.Integer,     default=0)
    ip_hash          = db.Column(db.String(64),  nullable=True)
    user_agent       = db.Column(db.String(500), nullable=True)
    device_type      = db.Column(db.Enum('desktop', 'tablet', 'mobile', 'bot', 'unknown'),
                                 nullable=False, default='unknown')
    browser          = db.Column(db.String(80),  nullable=True)
    os               = db.Column(db.String(80),  nullable=True)
    referrer_url     = db.Column(db.String(1000), nullable=True)
    referrer_domain  = db.Column(db.String(200), nullable=True)
    referrer_type    = db.Column(db.Enum('direct', 'organic', 'social', 'referral',
                                         'email', 'paid', 'unknown'),
                                 nullable=False, default='unknown')
    utm_source       = db.Column(db.String(200), nullable=True)
    utm_medium       = db.Column(db.String(200), nullable=True)
    utm_campaign     = db.Column(db.String(200), nullable=True)
    utm_content      = db.Column(db.String(200), nullable=True)
    country          = db.Column(db.String(80),  nullable=True)
    region           = db.Column(db.String(80),  nullable=True)
    city             = db.Column(db.String(80),  nullable=True)
    is_bounce        = db.Column(db.Boolean,     default=True)
    consent_given    = db.Column(db.Boolean,     default=False)

    __table_args__ = (
        db.Index('ix_site_sessions_started_at', 'started_at'),
        db.Index('ix_site_sessions_ip_hash',    'ip_hash'),
        db.Index('ix_site_sessions_user_id',    'user_id'),
    )


# ── Analytics: Page Views ─────────────────────────────────────────────────────

class PageView(db.Model):
    __tablename__ = 'page_views'

    view_id              = db.Column(db.String(9),   primary_key=True, default=generate_pk)
    session_id           = db.Column(db.String(9),   db.ForeignKey('site_sessions.session_id'), nullable=True)
    user_id              = db.Column(db.String(9),   db.ForeignKey('users.user_id'), nullable=True)
    url_path             = db.Column(db.String(500), nullable=False)
    url_query            = db.Column(db.String(500), nullable=True)
    page_title           = db.Column(db.String(200), nullable=True)
    http_method          = db.Column(db.Enum('GET', 'POST'), nullable=False, default='GET')
    http_status          = db.Column(db.SmallInteger, nullable=False, default=200)
    response_time_ms     = db.Column(db.Integer,     nullable=True)
    referrer_path        = db.Column(db.String(500), nullable=True)
    time_on_page_seconds = db.Column(db.Integer,     nullable=True)
    viewed_at            = db.Column(db.DateTime,    nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.Index('ix_page_views_session_id', 'session_id'),
        db.Index('ix_page_views_viewed_at',  'viewed_at'),
        db.Index('ix_page_views_url_path',   'url_path'),
    )


# ── Analytics: User Events ────────────────────────────────────────────────────

class UserEvent(db.Model):
    __tablename__ = 'user_events'

    event_id       = db.Column(db.String(9),   primary_key=True, default=generate_pk)
    session_id     = db.Column(db.String(9),   db.ForeignKey('site_sessions.session_id'), nullable=True)
    user_id        = db.Column(db.String(9),   db.ForeignKey('users.user_id'), nullable=True)
    event_type     = db.Column(db.String(80),  nullable=False)
    event_category = db.Column(db.String(50),  nullable=False)
    url_path       = db.Column(db.String(500), nullable=False)
    target_id      = db.Column(db.String(9),   nullable=True)
    target_type    = db.Column(db.String(50),  nullable=True)
    event_meta     = db.Column('metadata', db.Text, nullable=True)   # JSON string
    occurred_at    = db.Column(db.DateTime,    nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.Index('ix_user_events_session_id',  'session_id'),
        db.Index('ix_user_events_user_id',     'user_id'),
        db.Index('ix_user_events_event_type',  'event_type'),
        db.Index('ix_user_events_occurred_at', 'occurred_at'),
    )


# ── Analytics: Daily Stats (aggregated nightly) ───────────────────────────────

class DailyStat(db.Model):
    __tablename__ = 'daily_stats'

    stat_id               = db.Column(db.String(9),       primary_key=True, default=generate_pk)
    stat_date             = db.Column(db.Date,            unique=True, nullable=False)
    total_sessions        = db.Column(db.Integer,         default=0)
    total_page_views      = db.Column(db.Integer,         default=0)
    unique_visitors       = db.Column(db.Integer,         default=0)
    new_vs_returning      = db.Column(db.Text,            nullable=True)
    bounce_rate           = db.Column(db.Numeric(5, 2),   nullable=True)
    avg_session_duration  = db.Column(db.Integer,         nullable=True)
    avg_pages_per_session = db.Column(db.Numeric(4, 2),   nullable=True)
    device_breakdown      = db.Column(db.Text,            nullable=True)
    browser_breakdown     = db.Column(db.Text,            nullable=True)
    referrer_breakdown    = db.Column(db.Text,            nullable=True)
    top_pages             = db.Column(db.Text,            nullable=True)
    top_experiences       = db.Column(db.Text,            nullable=True)
    booking_funnel        = db.Column(db.Text,            nullable=True)
    bookings_completed    = db.Column(db.Integer,         default=0)
    revenue_total         = db.Column(db.Numeric(10, 2),  default=0.00)
    new_accounts          = db.Column(db.Integer,         default=0)
    contact_submissions   = db.Column(db.Integer,         default=0)
    chat_sessions_started = db.Column(db.Integer,         default=0)
    error_404_count       = db.Column(db.Integer,         default=0)
    error_500_count       = db.Column(db.Integer,         default=0)
    computed_at           = db.Column(db.DateTime,        nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.Index('ix_daily_stats_stat_date', 'stat_date'),
    )


# ── Analytics: Experience Stats (aggregated nightly) ─────────────────────────

class ExperienceStat(db.Model):
    __tablename__ = 'experience_stats'

    stat_id            = db.Column(db.String(9),      primary_key=True, default=generate_pk)
    experience_id      = db.Column(db.String(9),      db.ForeignKey('experiences.experience_id'), nullable=False)
    stat_date          = db.Column(db.Date,           nullable=False)
    views              = db.Column(db.Integer,        default=0)
    booking_starts     = db.Column(db.Integer,        default=0)
    bookings_completed = db.Column(db.Integer,        default=0)
    conversion_rate    = db.Column(db.Numeric(5, 2),  nullable=True)
    revenue            = db.Column(db.Numeric(10, 2), default=0.00)
    avg_time_on_page   = db.Column(db.Integer,        nullable=True)
    cart_adds          = db.Column(db.Integer,        default=0)
    abandonment_rate   = db.Column(db.Numeric(5, 2),  nullable=True)

    __table_args__ = (
        db.Index('ix_experience_stats_experience_id', 'experience_id'),
        db.Index('ix_experience_stats_stat_date',     'stat_date'),
    )


# ── Analytics: Funnel Steps ───────────────────────────────────────────────────

class FunnelStep(db.Model):
    __tablename__ = 'funnel_steps'

    step_id              = db.Column(db.String(9),  primary_key=True, default=generate_pk)
    session_id           = db.Column(db.String(9),  db.ForeignKey('site_sessions.session_id'), nullable=True)
    experience_id        = db.Column(db.String(9),  db.ForeignKey('experiences.experience_id'), nullable=True)
    step_name            = db.Column(db.Enum('experience_view', 'booking_start', 'timeslot_select',
                                              'cart_add', 'checkout_start', 'payment_attempt',
                                              'booking_complete'), nullable=False)
    step_order           = db.Column(db.SmallInteger, nullable=False)
    entered_at           = db.Column(db.DateTime,   nullable=False, default=lambda: datetime.now(timezone.utc))
    exited_at            = db.Column(db.DateTime,   nullable=True)
    time_at_step_seconds = db.Column(db.Integer,    nullable=True)
    completed            = db.Column(db.Boolean,    default=False)

    __table_args__ = (
        db.Index('ix_funnel_steps_session_id', 'session_id'),
        db.Index('ix_funnel_steps_entered_at', 'entered_at'),
    )


# ── Analytics: UTM Campaigns (aggregated nightly) ────────────────────────────

class UtmCampaign(db.Model):
    __tablename__ = 'utm_campaigns'

    campaign_id          = db.Column(db.String(9),      primary_key=True, default=generate_pk)
    utm_source           = db.Column(db.String(200),    nullable=False)
    utm_medium           = db.Column(db.String(200),    nullable=False)
    utm_campaign         = db.Column(db.String(200),    nullable=False)
    stat_date            = db.Column(db.Date,           nullable=False)
    sessions             = db.Column(db.Integer,        default=0)
    page_views           = db.Column(db.Integer,        default=0)
    bookings_completed   = db.Column(db.Integer,        default=0)
    revenue              = db.Column(db.Numeric(10, 2), default=0.00)
    bounce_rate          = db.Column(db.Numeric(5, 2),  nullable=True)
    avg_session_duration = db.Column(db.Integer,        nullable=True)

    __table_args__ = (
        db.Index('ix_utm_campaigns_stat_date', 'stat_date'),
        db.UniqueConstraint('utm_source', 'utm_medium', 'utm_campaign', 'stat_date',
                            name='uq_utm_campaign_date'),
    )
