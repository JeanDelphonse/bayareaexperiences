"""
Build the dynamic system prompt context injected into each Claude request.
"""
from app.models import Experience, Booking


SYSTEM_PROMPT_TEMPLATE = """\
You are the Bay Area Experiences virtual assistant — a friendly, concise, and knowledgeable helper \
for a premium small-group tour and private transport service in the San Francisco Bay Area.

## Your Role
- Answer questions about services, pricing, pickup locations, durations, and policies
- Help visitors understand which experience best fits their needs
- For authenticated users, answer questions about their personal booking history
- Gracefully escalate when questions are outside your knowledge scope

## Hard Rules
- NEVER fabricate pricing, availability, or service details not listed below
- NEVER discuss competitors, politics, or topics unrelated to Bay Area Experiences
- NEVER mention payment card details, passwords, or other sensitive data
- NEVER make, modify, or cancel bookings directly — direct users to the website
- Keep responses concise (2–4 sentences unless more detail is explicitly requested)
- If unsure, say: "For the most accurate answer, please contact us via the contact form \
or call (408) 831-2101."

## Escalation
If a user expresses frustration, urgency, or needs a human, respond with empathy and direct them to:
- Contact form: bayareaexperiences.com/contact
- Phone / text: (408) 831-2101

## Knowledge Base — Active Services
{knowledge_base}

## Current User
{user_context}
"""


def build_system_prompt(user=None):
    kb = _build_knowledge_base()
    uc = _build_user_context(user)
    return SYSTEM_PROMPT_TEMPLATE.format(knowledge_base=kb, user_context=uc)


def _build_knowledge_base():
    exps = Experience.query.filter_by(is_active=True).order_by(Experience.sort_order).all()
    if not exps:
        return "No active services found."
    lines = []
    for exp in exps:
        cities = ', '.join(loc.pickup_city for loc in exp.pickup_locations)
        lines.append(
            f"**{exp.name}** ({exp.category})\n"
            f"  Price: ${float(exp.price):.2f} per booking | Duration: {exp.duration_hours} hrs | "
            f"Max guests: {exp.max_guests} | Advance booking: {exp.advance_booking_days} day(s)\n"
            f"  Pickup cities: {cities or 'Contact us'}\n"
            f"  {exp.description[:180] if exp.description else ''}..."
        )
    return '\n\n'.join(lines)


def _build_user_context(user):
    if user is None or not getattr(user, 'is_authenticated', False):
        return "Guest (not logged in) — do not reveal any personal booking data."

    bookings = (Booking.query
                .filter_by(user_id=user.user_id)
                .order_by(Booking.created_at.desc())
                .limit(10).all())

    if not bookings:
        return f"Authenticated user: {user.first_name} {user.last_name} — no bookings on file."

    lines = [f"Authenticated user: {user.first_name} {user.last_name} (ID: {user.user_id})"]
    lines.append("Recent bookings (up to 10):")
    for b in bookings:
        lines.append(
            f"  • Booking {b.booking_id}: {b.experience.name} | "
            f"{b.timeslot.slot_date} {b.timeslot.start_time.strftime('%I:%M %p')} | "
            f"Status: {b.booking_status} | Paid: ${float(b.amount_paid):.2f} | "
            f"Due: ${float(b.amount_due):.2f} | Pickup: {b.pickup_city}"
        )
    return '\n'.join(lines)
