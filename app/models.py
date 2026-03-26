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

    staff_id                   = db.Column(db.String(9),   primary_key=True, default=generate_pk)
    full_name                  = db.Column(db.String(150), nullable=False)
    title                      = db.Column(db.String(100))
    phone                      = db.Column(db.String(30))
    email                      = db.Column(db.String(150), unique=True, nullable=False)
    notes                      = db.Column(db.Text)
    is_active                  = db.Column(db.Boolean, default=True)
    user_id                    = db.Column(db.String(9),   db.ForeignKey('users.user_id'), nullable=True)
    staff_portal_token         = db.Column(db.String(64),  nullable=True)
    staff_portal_token_expires = db.Column(db.DateTime,    nullable=True)
    created_at                 = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref='bae_staff_record', foreign_keys=[user_id])


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

    # Marketplace additions
    provider_id          = db.Column(db.String(9),   db.ForeignKey('providers.provider_id'), nullable=True)
    short_description    = db.Column(db.String(200), nullable=True)
    inclusions           = db.Column(db.Text,        nullable=True)
    what_to_bring        = db.Column(db.Text,        nullable=True)
    cancellation_policy  = db.Column(db.Enum('flexible', 'moderate', 'strict'), nullable=True)
    listing_status       = db.Column(db.Enum('draft', 'pending_review', 'active'), nullable=False, default='active')

    # Reviews aggregate (updated on each new published review)
    avg_star_rating  = db.Column(db.Numeric(3, 2),  nullable=True)
    review_count     = db.Column(db.Integer, nullable=False, default=0)

    # AI itinerary generation
    core_stops       = db.Column(db.Text,        nullable=True)

    staff        = db.relationship('StaffMember', backref='experiences')
    timeslots    = db.relationship('Timeslot', backref='experience', lazy='dynamic')
    pickup_locations = db.relationship('ExperiencePickupLocation', backref='experience',
                                        cascade='all, delete-orphan')
    provider     = db.relationship('Provider', backref='experiences', foreign_keys=[provider_id])

    __table_args__ = (
        db.Index('ix_experiences_slug', 'slug'),
        db.Index('ix_experiences_sort_order', 'sort_order'),
        db.Index('ix_experiences_provider_id', 'provider_id'),
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
    staff_id              = db.Column(db.String(9),   db.ForeignKey('staff_members.staff_id'), nullable=True)
    provider_staff_id     = db.Column(db.String(9),   db.ForeignKey('provider_staff_members.provider_staff_id'), nullable=True)

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

    # Marketplace: payment split columns
    platform_fee_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    provider_amount     = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)

    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    experience     = db.relationship('Experience',          backref='bookings')
    timeslot       = db.relationship('Timeslot',            backref='bookings')
    staff          = db.relationship('StaffMember',         backref='bookings', foreign_keys=[staff_id])
    provider_staff = db.relationship('ProviderStaffMember', backref='bookings', foreign_keys=[provider_staff_id])
    review_tokens  = db.relationship('ReviewToken', backref='booking', lazy='dynamic')

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

# ── Marketplace: Providers ────────────────────────────────────────────────────

class Provider(db.Model):
    __tablename__ = 'providers'

    provider_id             = db.Column(db.String(9),    primary_key=True, default=generate_pk)
    user_id                 = db.Column(db.String(9),    db.ForeignKey('users.user_id'), nullable=False, unique=True)

    # Business identity
    business_name           = db.Column(db.String(200),  nullable=False)
    business_slug           = db.Column(db.String(100),  nullable=False, unique=True)
    bio                     = db.Column(db.Text,          nullable=True)
    headshot_url            = db.Column(db.String(500),  nullable=True)
    cover_photo_url         = db.Column(db.String(500),  nullable=True)
    website                 = db.Column(db.String(300),  nullable=True)
    instagram               = db.Column(db.String(200),  nullable=True)
    languages_spoken        = db.Column(db.String(200),  nullable=True)
    years_experience        = db.Column(db.Integer,       nullable=True)
    service_cities          = db.Column(db.String(500),  nullable=True)   # comma-separated

    # Application fields
    phone                   = db.Column(db.String(30),   nullable=True)
    experience_types        = db.Column(db.String(500),  nullable=True)   # what kind of tours
    why_join                = db.Column(db.Text,          nullable=True)

    # Tier & commission
    tier                    = db.Column(db.Enum('free', 'pro'), nullable=False, default='free')
    commission_rate         = db.Column(db.Numeric(4, 2), nullable=False, default=20.00)
    processing_fee_rate     = db.Column(db.Numeric(4, 2), nullable=False, default=5.00)
    experience_limit        = db.Column(db.Integer,       nullable=False, default=5)

    # Stripe Connect
    stripe_account_id       = db.Column(db.String(200),  nullable=True)
    stripe_customer_id      = db.Column(db.String(200),  nullable=True)
    stripe_onboarding_complete = db.Column(db.Boolean,   nullable=False, default=False)

    # Pro subscription
    subscription_id         = db.Column(db.String(200),  nullable=True)
    subscription_status     = db.Column(db.String(50),   nullable=True)
    subscription_plan       = db.Column(db.Enum('monthly', 'annual'), nullable=True)
    current_period_end      = db.Column(db.DateTime,     nullable=True)

    # Verification & status
    is_verified             = db.Column(db.Boolean,       nullable=False, default=False)
    verification_level      = db.Column(db.Enum('none', 'basic', 'enhanced'), nullable=False, default='none')
    can_list_experiences    = db.Column(db.Boolean,       nullable=False, default=False)
    first_listing_approved  = db.Column(db.Boolean,       nullable=False, default=False)
    is_active               = db.Column(db.Boolean,       nullable=False, default=True)
    rejection_reason        = db.Column(db.Text,          nullable=True)

    # Timestamps
    applied_at              = db.Column(db.DateTime,      nullable=False, default=lambda: datetime.now(timezone.utc))
    approved_at             = db.Column(db.DateTime,      nullable=True)
    approved_by             = db.Column(db.String(9),     nullable=True)
    activated_at            = db.Column(db.DateTime,      nullable=True)

    user = db.relationship('User', backref=db.backref('provider', uselist=False))

    __table_args__ = (
        db.Index('ix_providers_user_id',       'user_id'),
        db.Index('ix_providers_business_slug', 'business_slug'),
        db.Index('ix_providers_tier',          'tier'),
        db.Index('ix_providers_is_active',     'is_active'),
    )

    @property
    def effective_commission_rate(self):
        if self.tier == 'pro':
            return float(self.processing_fee_rate)
        return float(self.commission_rate)

    @property
    def display_name(self):
        return self.business_name

    @property
    def is_enhanced_verified(self):
        return self.verification_level == 'enhanced' and self.tier == 'pro'


# ── Marketplace: Provider Verification Documents ──────────────────────────────

class ProviderVerificationDoc(db.Model):
    __tablename__ = 'provider_verification_docs'

    doc_id            = db.Column(db.String(9),   primary_key=True, default=generate_pk)
    provider_id       = db.Column(db.String(9),   db.ForeignKey('providers.provider_id'), nullable=False)
    doc_type          = db.Column(db.Enum('government_id', 'business_license', 'insurance',
                                          'vehicle_registration', 'background_check'), nullable=False)
    file_path         = db.Column(db.String(500), nullable=False)
    original_filename = db.Column(db.String(200), nullable=False)
    file_size         = db.Column(db.Integer,     nullable=True)
    status            = db.Column(db.Enum('pending', 'approved', 'rejected'), nullable=False, default='pending')
    rejection_reason  = db.Column(db.Text,        nullable=True)
    expires_at        = db.Column(db.Date,         nullable=True)
    reviewed_by       = db.Column(db.String(9),   nullable=True)
    reviewed_at       = db.Column(db.DateTime,    nullable=True)
    uploaded_at       = db.Column(db.DateTime,    nullable=False, default=lambda: datetime.now(timezone.utc))

    provider = db.relationship('Provider', backref='verification_docs')

    __table_args__ = (
        db.Index('ix_provider_docs_provider_id', 'provider_id'),
        db.Index('ix_provider_docs_status',      'status'),
    )


# ── Marketplace: Provider Payouts ─────────────────────────────────────────────

class ProviderPayout(db.Model):
    __tablename__ = 'provider_payouts'

    payout_id                = db.Column(db.String(9),      primary_key=True, default=generate_pk)
    provider_id              = db.Column(db.String(9),      db.ForeignKey('providers.provider_id'), nullable=False)
    booking_id               = db.Column(db.String(9),      db.ForeignKey('bookings.booking_id'), nullable=False)
    booking_amount           = db.Column(db.Numeric(10, 2), nullable=False)
    platform_fee             = db.Column(db.Numeric(10, 2), nullable=False)
    provider_amount          = db.Column(db.Numeric(10, 2), nullable=False)
    stripe_payment_intent_id = db.Column(db.String(200),    nullable=False)
    stripe_transfer_id       = db.Column(db.String(200),    nullable=True)
    stripe_transfer_status   = db.Column(db.Enum('pending', 'paid', 'failed'), nullable=False, default='pending')
    tier_at_time             = db.Column(db.Enum('free', 'pro'), nullable=False, default='free')
    commission_rate_applied  = db.Column(db.Numeric(4, 2),  nullable=False)
    transfer_completed_at    = db.Column(db.DateTime,       nullable=True)
    created_at               = db.Column(db.DateTime,       nullable=False, default=lambda: datetime.now(timezone.utc))

    provider = db.relationship('Provider', backref='payouts')
    booking  = db.relationship('Booking',  backref='payout')

    __table_args__ = (
        db.Index('ix_provider_payouts_provider_id', 'provider_id'),
        db.Index('ix_provider_payouts_booking_id',  'booking_id'),
        db.Index('ix_provider_payouts_created_at',  'created_at'),
    )


# ── Reviews ────────────────────────────────────────────────────────────────────

class ExperienceReview(db.Model):
    __tablename__ = 'experience_reviews'

    review_id                  = db.Column(db.String(9),   primary_key=True, default=generate_pk)
    booking_id                 = db.Column(db.String(9),   db.ForeignKey('bookings.booking_id'), unique=True, nullable=False)
    experience_id              = db.Column(db.String(9),   db.ForeignKey('experiences.experience_id'), nullable=False)
    user_id                    = db.Column(db.String(9),   db.ForeignKey('users.user_id'), nullable=True)
    provider_id                = db.Column(db.String(9),   db.ForeignKey('providers.provider_id'), nullable=True)
    star_rating                = db.Column(db.SmallInteger, nullable=False)
    best_moment                = db.Column(db.Text,        nullable=False)
    reviewer_first_name        = db.Column(db.String(80),  nullable=False)
    reviewer_last_name_initial = db.Column(db.String(1),   nullable=False)
    reviewer_display_name      = db.Column(db.String(100), nullable=False)
    is_verified_booking        = db.Column(db.Boolean,     default=True)
    status                     = db.Column(db.Enum('pending', 'published', 'held', 'flagged', 'removed'),
                                           nullable=False, default='pending')
    published_at               = db.Column(db.DateTime,   nullable=True)
    held_until                 = db.Column(db.DateTime,   nullable=True)
    is_featured                = db.Column(db.Boolean,    default=False)
    helpful_count              = db.Column(db.Integer,    default=0)
    flag_count                 = db.Column(db.Integer,    default=0)
    provider_response          = db.Column(db.Text,       nullable=True)
    provider_response_at       = db.Column(db.DateTime,  nullable=True)
    admin_notes                = db.Column(db.Text,       nullable=True)
    feedback_token_id          = db.Column(db.String(9),  db.ForeignKey('review_tokens.token_id'), nullable=True)
    submitted_at               = db.Column(db.DateTime,  nullable=False, default=lambda: datetime.now(timezone.utc))
    ip_address                 = db.Column(db.String(45), nullable=True)

    booking    = db.relationship('Booking',    backref=db.backref('review', uselist=False))
    experience = db.relationship('Experience', backref='reviews')
    user       = db.relationship('User',       backref='reviews')

    __table_args__ = (
        db.Index('ix_reviews_experience_id', 'experience_id'),
        db.Index('ix_reviews_status',        'status'),
        db.Index('ix_reviews_submitted_at',  'submitted_at'),
    )


class ReviewToken(db.Model):
    __tablename__ = 'review_tokens'

    token_id      = db.Column(db.String(9),   primary_key=True, default=generate_pk)
    token         = db.Column(db.String(64),  unique=True, nullable=False)
    booking_id    = db.Column(db.String(9),   db.ForeignKey('bookings.booking_id'), unique=True, nullable=False)
    experience_id = db.Column(db.String(9),   db.ForeignKey('experiences.experience_id'), nullable=False)
    user_id       = db.Column(db.String(9),   db.ForeignKey('users.user_id'), nullable=True)
    email_sent_to = db.Column(db.String(150), nullable=False)
    email_sent_at = db.Column(db.DateTime,   nullable=True)
    is_used       = db.Column(db.Boolean,    default=False)
    used_at       = db.Column(db.DateTime,   nullable=True)
    expires_at    = db.Column(db.DateTime,   nullable=False)
    created_at    = db.Column(db.DateTime,   nullable=False, default=lambda: datetime.now(timezone.utc))

    experience = db.relationship('Experience', backref='review_tokens')
    user       = db.relationship('User',       backref='review_tokens')

    __table_args__ = (
        db.Index('ix_review_tokens_token',      'token'),
        db.Index('ix_review_tokens_booking_id', 'booking_id'),
    )


class ReviewVote(db.Model):
    __tablename__ = 'review_votes'

    vote_id   = db.Column(db.String(9),  primary_key=True, default=generate_pk)
    review_id = db.Column(db.String(9),  db.ForeignKey('experience_reviews.review_id'), nullable=False)
    user_id   = db.Column(db.String(9),  db.ForeignKey('users.user_id'), nullable=True)
    ip_address = db.Column(db.String(45), nullable=False)
    voted_at  = db.Column(db.DateTime,   nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.Index('ix_review_votes_review_id', 'review_id'),
    )


class ReviewFlag(db.Model):
    __tablename__ = 'review_flags'

    flag_id              = db.Column(db.String(9),  primary_key=True, default=generate_pk)
    review_id            = db.Column(db.String(9),  db.ForeignKey('experience_reviews.review_id'), nullable=False)
    reported_by_user_id  = db.Column(db.String(9),  db.ForeignKey('users.user_id'), nullable=True)
    reported_by_ip       = db.Column(db.String(45), nullable=False)
    reason               = db.Column(db.Enum('fake', 'offensive', 'spam', 'irrelevant', 'other'), nullable=False)
    notes                = db.Column(db.Text,       nullable=True)
    flagged_at           = db.Column(db.DateTime,   nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.Index('ix_review_flags_review_id', 'review_id'),
    )


# ── Booking Itineraries ────────────────────────────────────────────────────────

class BookingItinerary(db.Model):
    __tablename__ = 'booking_itineraries'

    itinerary_id       = db.Column(db.String(9),   primary_key=True, default=generate_pk)
    booking_id         = db.Column(db.String(9),   db.ForeignKey('bookings.booking_id'), nullable=False)
    version            = db.Column(db.SmallInteger, nullable=False, default=1)
    is_active          = db.Column(db.Boolean,      nullable=False, default=True)
    itinerary_json     = db.Column(db.Text,         nullable=False)
    pickup_city        = db.Column(db.String(100),  nullable=False)
    tour_date          = db.Column(db.Date,         nullable=False)
    local_events_found = db.Column(db.SmallInteger, nullable=False, default=0)
    ticketmaster_events = db.Column(db.Text,        nullable=True)
    eventbrite_events  = db.Column(db.Text,         nullable=True)
    is_fallback        = db.Column(db.Boolean,      nullable=False, default=False)
    generation_trigger = db.Column(
        db.Enum('booking_confirmed', '48hr_refresh', 'manual_regen', 'admin'),
        nullable=False, default='booking_confirmed')
    generated_at       = db.Column(db.DateTime,     nullable=False,
                                   default=lambda: datetime.now(timezone.utc))
    staff_notified_at  = db.Column(db.DateTime,     nullable=True)

    booking = db.relationship('Booking', backref='itineraries')

    __table_args__ = (
        db.Index('ix_booking_itineraries_booking_id', 'booking_id'),
        db.Index('ix_booking_itineraries_tour_date', 'tour_date'),
    )


# ── Staff: Provider Staff Members ─────────────────────────────────────────────

class ProviderStaffMember(db.Model):
    __tablename__ = 'provider_staff_members'

    provider_staff_id          = db.Column(db.String(9),   primary_key=True, default=generate_pk)
    provider_id                = db.Column(db.String(9),   db.ForeignKey('providers.provider_id'), nullable=False)
    user_id                    = db.Column(db.String(9),   db.ForeignKey('users.user_id'), nullable=True)
    first_name                 = db.Column(db.String(80),  nullable=False)
    last_name                  = db.Column(db.String(80),  nullable=False)
    full_name                  = db.Column(db.String(160), nullable=False)
    title                      = db.Column(db.String(100), nullable=True)
    email                      = db.Column(db.String(150), nullable=False)
    phone                      = db.Column(db.String(30),  nullable=True)
    bio                        = db.Column(db.Text,        nullable=True)
    photo_url                  = db.Column(db.String(500), nullable=True)
    languages_spoken           = db.Column(db.String(200), nullable=True)
    is_active                  = db.Column(db.Boolean,     nullable=False, default=True)
    can_login                  = db.Column(db.Boolean,     nullable=False, default=False)
    staff_portal_token         = db.Column(db.String(64),  nullable=True)
    staff_portal_token_expires = db.Column(db.DateTime,    nullable=True)
    notes                      = db.Column(db.Text,        nullable=True)
    created_at                 = db.Column(db.DateTime,    nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at                 = db.Column(db.DateTime,    nullable=False, default=lambda: datetime.now(timezone.utc),
                                           onupdate=lambda: datetime.now(timezone.utc))

    provider = db.relationship('Provider', backref='staff_members')
    user     = db.relationship('User',     backref='provider_staff_records', foreign_keys=[user_id])

    __table_args__ = (
        db.Index('ix_provider_staff_provider_id', 'provider_id'),
        db.Index('ix_provider_staff_is_active',   'is_active'),
    )


# ── Staff: Assignment Log ──────────────────────────────────────────────────────

class StaffAssignmentLog(db.Model):
    __tablename__ = 'staff_assignment_log'

    log_id                     = db.Column(db.String(9),  primary_key=True, default=generate_pk)
    booking_id                 = db.Column(db.String(9),  db.ForeignKey('bookings.booking_id'), nullable=False)
    changed_by_user_id         = db.Column(db.String(9),  db.ForeignKey('users.user_id'), nullable=False)
    changed_by_role            = db.Column(db.Enum('admin', 'provider'), nullable=False)
    previous_staff_id          = db.Column(db.String(9),  nullable=True)
    new_staff_id               = db.Column(db.String(9),  nullable=True)
    previous_provider_staff_id = db.Column(db.String(9),  nullable=True)
    new_provider_staff_id      = db.Column(db.String(9),  nullable=True)
    reason                     = db.Column(db.String(300), nullable=True)
    changed_at                 = db.Column(db.DateTime,   nullable=False, default=lambda: datetime.now(timezone.utc))

    booking    = db.relationship('Booking', backref='assignment_logs')
    changed_by = db.relationship('User', backref='staff_assignment_logs', foreign_keys=[changed_by_user_id])

    __table_args__ = (
        db.Index('ix_staff_assignment_log_booking_id', 'booking_id'),
        db.Index('ix_staff_assignment_log_changed_at', 'changed_at'),
    )
