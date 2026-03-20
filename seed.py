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
load_dotenv()

from app import create_app
from app.extensions import db, bcrypt
from app.models import StaffMember, Experience, ExperiencePickupLocation, User
from app.utils import generate_pk

app = create_app('development')

PICKUP_CITIES = ['San Francisco, CA', 'San Jose, CA', 'Santa Cruz, CA', 'Monterey, CA']

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
        photo_url='/static/images/sf_city_icons.jpg',
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
        photo_url='/static/images/coastal_charm.jpg',
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
        photo_url='/static/images/wine_country.jpg',
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
        photo_url='/static/images/hiking_bay.jpg',
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
        photo_url='/static/images/silicon_valley.jpg',
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
        photo_url='/static/images/east_bay.jpg',
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
        photo_url='/static/images/jeepWrangler.webp',
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
        photo_url='/static/images/jeepWrangler.webp',
        sort_order=8,
    ),
]


def run_seed():
    with app.app_context():
        # Clear existing data
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
        for exp_data in EXPERIENCES:
            exp = Experience(
                experience_id=generate_pk(),
                payment_mode='full',
                max_guests=4,
                advance_booking_days=1,
                is_active=True,
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

        # ── Admin User ────────────────────────────────────────────────────────
        admin_password = os.environ.get('ADMIN_PASSWORD', 'ChangeMe123!')
        admin = User(
            user_id=generate_pk(),
            first_name='Admin',
            last_name='BAE',
            email=os.environ.get('ADMIN_EMAIL', 'admin@bayareaexperiences.com'),
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
