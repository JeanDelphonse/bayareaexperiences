# CLAUDE.md — Bay Area Experiences

Flask booking platform replacing bayareaexperiences.com (currently GoDaddy Website Builder).

## Stack

- Flask 3.0.3, SQLAlchemy, MySQL (SQLite dev), Flask-Login, Flask-Bcrypt, Flask-Mail, Flask-WTF
- Bootstrap 5, Vanilla JS + Fetch API, SortableJS (admin drag-drop)
- Stripe (payments + Connect), Google reCAPTCHA v3 (/register), ics library (calendar downloads)
- Hosting: GoDaddy cPanel Passenger WSGI — entry point: `passenger_wsgi.py`

## Common Commands

```bash
# Run dev server
python run.py

# Seed the database
python seed.py

# Migrate scripts (run once as needed)
python migrate_reviews.py
python migrate_pickup_cities.py
python migrate_marketplace.py
python migrate_v3.py

# Deploy: zip must be named bayareaexperiences_deploy.zip
```

## Project Structure

```
app/
  blueprints/
    main/         # Public experience listing + detail pages
    auth/         # Register, login, logout (reCAPTCHA on register)
    booking/      # Booking flow
    cart/         # Cart
    checkout/     # Stripe checkout
    account/      # Customer account
    contact/      # Contact form
    chat/         # Chatbot routes
    payments/     # Stripe webhook + split payouts
    providers/    # Provider apply, onboarding, public profile, dashboard
    admin/        # Staff admin panel
    tracking/     # Pageview/session analytics
  models.py       # All SQLAlchemy models
  utils.py        # generate_pk(), send_email(), admin_required()
  extensions.py   # db, login_manager, bcrypt, mail, csrf
  chatbot/        # Intent classification, context, guard
  reviews/        # Review email, notifications, scheduler
  tracking/       # Device, geo, session, referrer, aggregator
templates/        # Mirrors blueprint names
static/
  css/custom.css
  js/admin_sort.js, booking.js
  images/
```

All PKs are 9-char uppercase alphanumeric via `generate_pk()` in `app/utils.py`.

## Providers Module

The providers module (`app/blueprints/providers/`) is a marketplace layer on top of the core booking platform. Third-party guides ("providers") can apply, onboard, list experiences, and get paid via Stripe Connect.

### Key files
| File | Purpose |
|---|---|
| `views.py` | Apply form, onboarding flow (tier → Stripe Connect → documents), public profile |
| `dashboard.py` | Provider dashboard: experiences CRUD, bookings list, earnings, profile edit, subscription |
| `forms.py` | `ProviderApplicationForm`, `ProviderExperienceForm`, `ProviderProfileForm`, `ProviderDocUploadForm` |
| `decorators.py` | `@provider_required`, `@provider_active_required`, `current_provider()` |

### Provider model fields (key ones)
- `tier`: `'free'` or `'pro'`
- `experience_limit`: free=3, pro=unlimited
- `is_active`: admin toggles this
- `can_list_experiences`: admin grants this after review
- `first_listing_approved`: once True, new listings go live immediately (skip pending_review)
- `stripe_account_id`: Stripe Express account for payouts
- `stripe_customer_id`: Stripe Customer for subscription billing
- `stripe_onboarding_complete`: True after Stripe details_submitted
- `business_slug`: URL-safe unique slug, used at `/providers/<slug>`

### Provider onboarding flow
1. `/providers/apply` — submit application (must be logged in)
2. `/providers/onboarding/tier` — choose free or pro
3. `/providers/onboarding/stripe` — create Stripe Express account + redirect to Stripe
4. `/providers/onboarding/stripe/return` — confirm Stripe details submitted
5. `/providers/onboarding/documents` — upload verification docs (stored in `instance/provider_docs/<provider_id>/`)
6. Admin reviews and sets `is_active=True` + `can_list_experiences=True`

### Provider dashboard routes
| Route | Handler |
|---|---|
| `GET /provider/dashboard` | `dashboard()` — overview: stats + recent bookings |
| `GET /provider/dashboard/experiences` | `dashboard_experiences()` — list all experiences |
| `GET/POST /provider/dashboard/experiences/new` | `dashboard_experience_new()` |
| `GET/POST /provider/dashboard/experiences/<exp_id>/edit` | `dashboard_experience_edit()` |
| `POST /provider/dashboard/experiences/<exp_id>/toggle` | `dashboard_experience_toggle()` — activate/deactivate |
| `GET /provider/dashboard/bookings` | `dashboard_bookings()` — paginated, filterable by status |
| `GET /provider/dashboard/earnings` | `dashboard_earnings()` — payouts history |
| `GET/POST /provider/dashboard/profile` | `dashboard_profile()` — edit business profile |
| `GET /provider/dashboard/subscription` | `dashboard_subscription()` |
| `POST /provider/dashboard/subscription/upgrade` | Stripe Checkout for pro plan |
| `POST /provider/dashboard/subscription/portal` | Stripe billing portal |
| `GET/POST /provider/dashboard/documents` | `dashboard_documents()` — upload/view verification docs |

### Experience listing status
- New provider first listing → `listing_status='pending_review'` until admin approves
- After `first_listing_approved=True` → new listings go live as `'active'` immediately
- `listing_status` values: `'active'`, `'pending_review'`, `'inactive'`

### Provider tiers
- **Free**: up to 3 experiences, basic profile
- **Pro**: unlimited experiences, priority listing — billed via Stripe subscription (`STRIPE_PRO_MONTHLY_PRICE_ID` / `STRIPE_PRO_ANNUAL_PRICE_ID`)

### Pickup cities (13 supported)
Cupertino, Fremont, Los Gatos, Menlo Park, Monterey, Mountain View, Palo Alto, Redwood City, San Francisco, San Jose, Santa Clara, Santa Cruz, Sunnyvale

Stored in `ExperiencePickupLocation` table (one row per city per experience). `_save_pickup_cities()` in `dashboard.py` replaces all rows on edit.

### Public provider profile
`GET /providers/<slug>` — shows provider bio + all their active experiences.

### Admin management of providers
Admin can approve/reject provider applications, toggle `is_active`, `can_list_experiences`, `first_listing_approved`, review verification docs, and approve/reject individual experience listings.

## Reviews Module

`app/reviews/` + `app/blueprints/reviews/` — post-booking review system.
- `ExperienceReview` model with statuses: `'held'`, `'flagged'`, `'approved'`, `'rejected'`
- Admin sees held/flagged counts on dashboard
- Email notifications via `app/reviews/email.py`
- Scheduler in `app/reviews/scheduler.py`

## Admin Panel

`/admin/` — requires `@admin_required` (staff only). Key sections:
- Dashboard (bookings, revenue, held/flagged reviews, unread contacts)
- Experiences (CRUD + timeslot management)
- Bookings (assign staff, status)
- Staff management
- Contact submissions
- Analytics (tracking data)
- Marketplace (provider management)
- Reviews (approve/flag/hold)

## Environment Variables

```
SECRET_KEY
DATABASE_URL          # SQLite default; MySQL in prod
STRIPE_SECRET_KEY
STRIPE_PUBLISHABLE_KEY
STRIPE_WEBHOOK_SECRET
STRIPE_PRO_MONTHLY_PRICE_ID
STRIPE_PRO_ANNUAL_PRICE_ID
MAIL_SERVER / MAIL_USERNAME / MAIL_PASSWORD
RECAPTCHA_PUBLIC_KEY / RECAPTCHA_PRIVATE_KEY
ADMIN_EMAIL
ANTHROPIC_API_KEY     # chatbot
```

## Pre-seeded Data (seed.py)

**Staff:** Marsel Abdullin, Jean Delphonse, Valeriia Delphonse

**8 Core Experiences:** SF City Icons ($465/5h), Coastal Charm ($825/10h), Wine Country ($705/8h), Hiking ($585/6h), Silicon Valley ($525/6h), East Bay ($625/7h), Destination 3h ($195), Destination 6h ($375)

## Image Assets

- `jeepWrangler.webp` — only confirmed CDN image, used as hero + transport cards
- Run `migrate_images.sh` to pull from CDN to `app/static/images/`
- Logo filename: NOT YET CONFIRMED — verify via DevTools on live site
