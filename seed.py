"""
seed.py — Populate database with:
  - 3 staff members (pre-seeded as per PRD §7.5.1)
  - 8 experiences (6 curated + 2 transport) with owner-confirmed pricing
  - 4 pickup locations per experience
  - 1 admin user
Run: python seed.py
"""
import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'), override=True)

from datetime import date, time, timedelta
from app import create_app
from app.extensions import db, bcrypt
from app.models import StaffMember, Experience, ExperiencePickupLocation, Timeslot, User
from app.utils import generate_pk

app = create_app('production')

PICKUP_CITIES = [
    'Cupertino, CA', 'Fremont, CA', 'Los Gatos, CA', 'Menlo Park, CA',
    'Monterey, CA', 'Mountain View, CA', 'Palo Alto, CA', 'Redwood City, CA',
    'San Francisco, CA', 'San Jose, CA', 'Santa Clara, CA', 'Santa Cruz, CA',
    'Sunnyvale, CA',
]

STAFF = [
    {'full_name': 'Marsel Abdullin',    'email': 'marsel@bayareaexperiences.com'},
    {'full_name': 'Jean Delphonse',     'email': 'jean@bayareaexperiences.com'},
    {'full_name': 'Valeriia Delphonse', 'email': 'valeriia@bayareaexperiences.com'},
]

EXPERIENCES = [
    dict(
        name='San Francisco — City Icons & Hidden Gems',
        slug='sf-city-icons',
        category='City Tour',
        description=(
            'Explore the soul of San Francisco on this 5-hour deep-dive through iconic landmarks '
            'and secret corners locals love. From the painted ladies to hidden staircases, '
            'Fisherman\'s Wharf to Mission murals — your expert guide reveals it all from the '
            'comfort of a private Jeep Wrangler with just your group of up to 4.'
        ),
        duration_hours=5.0,
        price=465.00,
        photo_url='sf_city_icons.webp',
        sort_order=1,
    ),
    dict(
        name='Coastal Charm & Scenic Drive',
        slug='coastal-charm',
        category='Scenic Drive',
        description=(
            'The ultimate California coastal road trip — 10 hours of Big Sur cliffs, '
            'Carmel-by-the-Sea charm, and the wild Pacific coast. Door-to-door in a Jeep Wrangler '
            'with snacks and water onboard. Maximum 4 guests ensures an intimate, personal experience.'
        ),
        duration_hours=10.0,
        price=825.00,
        photo_url='coastal_charm.webp',
        sort_order=2,
    ),
    dict(
        name='Wine Country & Redwood Giants',
        slug='wine-country-redwoods',
        category='Wine & Nature',
        description=(
            'Combine Napa or Sonoma wine tasting with a walk among ancient coastal redwoods. '
            'This 8-hour journey takes you from vineyards to cathedral groves, with expert '
            'guidance, door-to-door pickup, and complimentary refreshments throughout.'
        ),
        duration_hours=8.0,
        price=705.00,
        photo_url='wine_country.webp',
        sort_order=3,
    ),
    dict(
        name='Hiking Adventures & Bay Views',
        slug='hiking-bay-views',
        category='Outdoor / Hiking',
        description=(
            'Lace up for 6 hours of Bay Area trails with sweeping views of the Golden Gate, '
            'the Bay Bridge, and rolling hills. Marin Headlands, Mt. Tamalpais, or Point Reyes — '
            'your guide tailors the hike to your fitness level. Group of up to 4, private Jeep transport.'
        ),
        duration_hours=6.0,
        price=585.00,
        photo_url='hiking.webp',
        sort_order=4,
    ),
    dict(
        name='Silicon Valley Innovation Trail',
        slug='silicon-valley-trail',
        category='Tech & Culture',
        description=(
            'Go behind the logos of the world\'s most influential tech companies. '
            'Apple Park, Google\'s Googleplex, Facebook\'s campus, Stanford University — '
            'this 6-hour tour blends history, culture, and the future. Perfect for tech enthusiasts '
            'and entrepreneurs. Private group, Jeep Wrangler, door-to-door.'
        ),
        duration_hours=6.0,
        price=525.00,
        photo_url='innovation_trail.webp',
        sort_order=5,
    ),
    dict(
        name='East Bay Vibe — Arts, Views & Eats',
        slug='east-bay-vibe',
        category='Arts & Food',
        description=(
            'Cross the Bay to discover Oakland\'s thriving arts scene, Rockridge eateries, '
            'Berkeley\'s Telegraph Avenue, and panoramic views from Grizzly Peak. '
            '7 hours, private group up to 4, door-to-door pickup, with power snacks and water included.'
        ),
        duration_hours=7.0,
        price=625.00,
        photo_url='east_bay.webp',
        sort_order=6,
    ),
    dict(
        name='Destination — Up to 3 Hours Round Trip',
        slug='transport-3hr',
        category='Private Transport',
        description=(
            'Need a reliable, stylish ride? Our Jeep Wrangler takes you and up to 3 companions '
            'anywhere within 3 hours round trip. Airports, events, day trips — door-to-door, '
            'complimentary refreshments onboard.'
        ),
        duration_hours=3.0,
        price=195.00,
        photo_url='jeep.webp',
        sort_order=7,
    ),
    dict(
        name='Destination — Up to 6 Hours Round Trip',
        slug='transport-6hr',
        category='Private Transport',
        description=(
            'Extended private transport for longer day trips — up to 6 hours round trip in our '
            'signature Jeep Wrangler. Up to 4 guests, door-to-door, with complimentary '
            'power snacks and water throughout your journey.'
        ),
        duration_hours=6.0,
        price=375.00,
        photo_url='jeep.webp',
        sort_order=8,
    ),

    # ── Tier 1 Expansion Services (prices pending owner confirmation) ──────────
    dict(
        name='Airport Transfer (SFO / OAK / SJC)',
        slug='airport-transfer',
        category='Private Transport',
        description=(
            'Premium private airport transfer in our signature Jeep Wrangler. '
            'We pick you up door-to-door and deliver you to SFO, OAK, or SJC in style. '
            'Flat-rate pricing, complimentary refreshments on board, and zero stress — '
            'available from all four Bay Area pickup cities.'
        ),
        duration_hours=2.0,
        price=175.00,
        photo_url='jeep.webp',
        sort_order=9,
    ),
    dict(
        name='Cruise Terminal Transfer (Pier 27 & Pier 35)',
        slug='cruise-transfer',
        category='Private Transport',
        description=(
            'Arrive or depart in style with a private door-to-door transfer to the Port of San Francisco. '
            'We serve Pier 27 and Pier 35 with full luggage accommodation and an optional '
            '20-minute SF highlights preview on the way in from the pier — a perfect welcome to the city.'
        ),
        duration_hours=2.0,
        price=212.00,
        photo_url='jeep.webp',
        sort_order=10,
    ),
    dict(
        name='Corporate Team Outing',
        slug='corporate-team-outing',
        category='Corporate',
        description=(
            'An exclusive executive team outing tailored for up to 4 colleagues. '
            'Choose between a Wine Country & Redwood Giants journey or the Silicon Valley Innovation Trail — '
            'both re-imagined for corporate groups with a branded welcome snack bag, '
            'custom itinerary card, and dedicated guide. '
            'Weekday slots available. Invoice payment options for established companies.'
        ),
        duration_hours=7.0,
        price=845.00,
        photo_url='jeep.webp',
        sort_order=11,
    ),

    # ── Tier 2 Expansion Services (prices pending owner confirmation) ──────────
    dict(
        name='Sunrise / Sunset Photography Tour',
        slug='photo-tour',
        category='Photography',
        description=(
            'Capture San Francisco at its most stunning. Our private photography tour visits '
            'the Golden Gate Bridge at golden hour, Marin Headlands, Baker Beach, '
            'Palace of Fine Arts, and Crissy Field. '
            'Sunrise tour: 5:00 AM–9:00 AM. Sunset tour: 5:30 PM–9:30 PM. '
            'Photography guide on board, all skill levels welcome.'
        ),
        duration_hours=4.0,
        price=625.00,
        photo_url='jeep.webp',
        sort_order=12,
    ),
    dict(
        name='Celebration Package — Bachelorette & Birthday',
        slug='celebration-tour',
        category='Celebrations',
        description=(
            'Mark the occasion in unforgettable style. Our Wine Country & Redwood Giants route '
            're-imagined as a premium celebration experience — Jeep interior decoration, '
            'charcuterie board, champagne or sparkling water on board, custom itinerary card '
            'with guest names, and photo stops built into every moment. '
            'Available for bachelorette, birthday, anniversary, and engagement celebrations. '
            'Minimum 5 days advance booking required.'
        ),
        duration_hours=9.0,
        price=975.00,
        photo_url='jeep.webp',
        sort_order=13,
    ),
    dict(
        name='Full-Day Iconic Day Trip — Yosemite / Muir Woods / Big Sur',
        slug='iconic-day-trip',
        category='Day Trip',
        description=(
            'The ultimate Bay Area escape — a private full-day Jeep Wrangler journey to your '
            'choice of California\'s most iconic destinations. '
            'Route A: Yosemite National Park (April–October, 10–12 hrs). '
            'Route B: Muir Woods + Sausalito (year-round, 8–10 hrs). '
            'Route C: Big Sur / Highway 1 (dry season, 10–11 hrs). '
            'All routes include door-to-door pickup and complimentary refreshments throughout.'
        ),
        duration_hours=11.0,
        price=1145.00,
        photo_url='jeep.webp',
        sort_order=14,
    ),
    dict(
        name='SF After Dark — Night Tour',
        slug='sf-night-tour',
        category='Night Tour',
        description=(
            'San Francisco after dark is a completely different city. '
            'Experience the Bay Bridge LED light show, Twin Peaks cityscape, '
            'Embarcadero reflections, Chinatown lanterns, and Nob Hill by night. '
            'Depart 7:00 PM, return by 11:00 PM. '
            'Optional mid-tour restaurant dinner drop-off — guide waits, tour resumes. '
            'Private group of up to 4 guests.'
        ),
        duration_hours=4.0,
        price=495.00,
        photo_url='jeep.webp',
        sort_order=15,
    ),

    # ── Tier 3 Expansion Services (prices pending owner confirmation) ──────────
    dict(
        name='Monterey & Carmel Coast Day Trip',
        slug='monterey-carmel-day',
        category='Day Trip',
        description=(
            'A full-day journey along the legendary California coast. '
            'Depart San Francisco or San Jose at 8:00 AM and explore '
            'the Monterey Bay Aquarium, the world-famous 17-Mile Drive, '
            'and the charming village of Carmel-by-the-Sea — returning by 6:00 PM. '
            'Door-to-door pickup, complimentary refreshments, private Jeep Wrangler. '
            'Aquarium tickets not included; recommendations provided in your confirmation.'
        ),
        duration_hours=10.0,
        price=995.00,
        photo_url='jeep.webp',
        sort_order=16,
    ),
]


def run_seed():
    with app.app_context():
        # Clear existing data
        Timeslot.query.delete()
        ExperiencePickupLocation.query.delete()
        Experience.query.delete()
        StaffMember.query.delete()
        User.query.filter_by(is_admin=True).delete()
        db.session.commit()

        # ── Staff ─────────────────────────────────────────────────────────────
        for s in STAFF:
            staff = StaffMember(
                staff_id=generate_pk(),
                full_name=s['full_name'],
                email=s['email'],
                is_active=True,
            )
            db.session.add(staff)
        db.session.flush()
        print(f"  ✓ {len(STAFF)} staff members seeded")

        # ── Experiences ───────────────────────────────────────────────────────
        # Original 8 services (sort_order 1-8) are active; expansion services inactive pending price confirmation
        EXPANSION_SORT_ORDERS = set(range(9, 17))
        for exp_data in EXPERIENCES:
            is_active = exp_data.get('sort_order', 0) not in EXPANSION_SORT_ORDERS
            advance_days = 2 if exp_data.get('slug') in ('monterey-carmel-day', 'iconic-day-trip') else 1
            exp = Experience(
                experience_id=generate_pk(),
                payment_mode='full',
                max_guests=4,
                advance_booking_days=advance_days,
                is_active=is_active,
                **exp_data,
            )
            db.session.add(exp)
            db.session.flush()

            for city in PICKUP_CITIES:
                loc = ExperiencePickupLocation(
                    id=generate_pk(),
                    experience_id=exp.experience_id,
                    pickup_city=city,
                )
                db.session.add(loc)

        print(f"  ✓ {len(EXPERIENCES)} experiences seeded with {len(PICKUP_CITIES)} pickup cities each")

        # ── Timeslots — next 60 days, daily at 9:00 AM for each active experience ──
        active_exps = Experience.query.filter_by(is_active=True).all()
        today = date.today()
        slot_count = 0
        for exp in active_exps:
            duration = float(exp.duration_hours)
            start_h = 9
            end_h = start_h + int(duration)
            end_m = int((duration % 1) * 60)
            for day_offset in range(1, 61):
                slot_date = today + timedelta(days=day_offset)
                slot = Timeslot(
                    timeslot_id=generate_pk(),
                    experience_id=exp.experience_id,
                    slot_date=slot_date,
                    start_time=time(start_h, 0),
                    end_time=time(end_h % 24, end_m),
                    capacity=4,
                    booked_count=0,
                    is_available=True,
                )
                db.session.add(slot)
                slot_count += 1
        print(f"  ✓ {slot_count} timeslots seeded (60 days × {len(active_exps)} experiences, 9:00 AM daily)")

        # ── Admin User ────────────────────────────────────────────────────────
        admin_password = os.environ.get('ADMIN_PASSWORD', 'ChangeMe123!')
        admin = User(
            user_id=generate_pk(),
            first_name='Admin',
            last_name='BAE',
            email=os.environ.get('ADMIN_EMAIL', 'valuemanager.management@gmail.com'),
            password_hash=bcrypt.generate_password_hash(admin_password, rounds=12).decode('utf-8'),
            is_admin=True,
            email_verified=True,
        )
        db.session.add(admin)
        print(f"  ✓ Admin user seeded: {admin.email}")

        db.session.commit()
        print("\nSeed complete — 3 staff, 8 experiences, 1 admin user loaded.")


if __name__ == '__main__':
    run_seed()
