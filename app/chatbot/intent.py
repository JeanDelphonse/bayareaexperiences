"""
Keyword-based intent classification — zero API tokens consumed.
Returns one of 7 intent labels (or None if no match).
"""
import re

INTENT_PATTERNS = [
    ('booking_history', [
        r'my booking', r'my reservation', r'did i book', r'booking id',
        r'my order', r'my purchase',
    ]),
    ('escalation', [
        r'complaint', r'unhappy', r'not happy', r'disappointed', r'problem',
        r'speak to', r'talk to', r'human', r'call me', r'urgent',
    ]),
    ('policies', [
        r'cancel', r'refund', r'reschedule', r'change my booking', r'policy',
        r'no.show', r'weather',
    ]),
    ('pricing', [
        r'how much', r'price', r'cost', r'expensive', r'\$', r'fee', r'charge',
    ]),
    ('availability', [
        r'available', r'when can', r'\bbook\b', r'schedule', r'slots', r'open dates',
    ]),
    ('pickup_logistics', [
        r'pickup', r'pick.up', r'where.*meet', r'location', r'drop.?off',
        r'drive', r'address',
    ]),
    ('service_inquiry', [
        r'what tours', r'what experiences', r'what do you offer', r'tell me about',
        r'services', r'options',
    ]),
]


def classify_intent(text: str) -> str | None:
    lower = text.lower()
    for intent, patterns in INTENT_PATTERNS:
        for pat in patterns:
            if re.search(pat, lower):
                return intent
    return None
