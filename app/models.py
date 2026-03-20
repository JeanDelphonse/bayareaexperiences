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
