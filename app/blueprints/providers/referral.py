"""Provider referral code generation and lookup."""
import random
import string
from app.extensions import db


def _gen_suffix(k=6) -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=k))


def get_or_create_referral_code(provider) -> str:
    """Return the provider's existing referral code or generate a new one."""
    if provider.referral_code:
        return provider.referral_code

    from app.models import Provider
    slug_part = provider.business_slug.upper().replace('-', '')[:10]
    code = f'PROV-{slug_part}-{_gen_suffix()}'
    while Provider.query.filter_by(referral_code=code).first():
        code = f'PROV-{slug_part}-{_gen_suffix()}'

    provider.referral_code = code
    db.session.commit()
    return code
