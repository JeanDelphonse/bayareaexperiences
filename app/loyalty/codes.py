"""Discount and referral code generation."""
import os
import secrets
import string
from datetime import datetime, timezone, timedelta

from app.models import DiscountCode, VipCustomer
from app.utils import generate_pk

ALPHA = string.ascii_uppercase + string.digits

VIP_DISCOUNT_PCT   = float(os.environ.get('VIP_DISCOUNT_PERCENT', 15.0))
VIP_EXPIRY_DAYS    = int(os.environ.get('VIP_DISCOUNT_EXPIRY_DAYS', 365))
REF_DISCOUNT_PCT   = float(os.environ.get('REFERRAL_FRIEND_DISCOUNT_PCT', 10.0))
REF_CODE_EXPIRY    = int(os.environ.get('REFERRAL_FRIEND_CODE_EXPIRY_DAYS', 90))


def _random_suffix(n=6):
    return ''.join(secrets.choice(ALPHA) for _ in range(n))


def generate_vip_discount_code(user) -> DiscountCode:
    """Generate a single-use VIP15-XXXXXX discount code."""
    code_str = f'VIP15-{_random_suffix(6)}'
    while DiscountCode.query.filter_by(code=code_str).first():
        code_str = f'VIP15-{_random_suffix(6)}'
    return DiscountCode(
        code_id          = generate_pk(),
        code             = code_str,
        code_type        = 'vip_loyalty',
        discount_percent = VIP_DISCOUNT_PCT,
        for_user_id      = user.user_id,
        is_single_use    = True,
        max_uses         = 1,
        times_used       = 0,
        is_active        = True,
        expires_at       = datetime.now(timezone.utc) + timedelta(days=VIP_EXPIRY_DAYS),
    )


def generate_referral_friend_code(referred_by_vip) -> DiscountCode:
    """Generate a single-use 10% discount for a referred friend."""
    code_str = f'REF10-{_random_suffix(8)}'
    while DiscountCode.query.filter_by(code=code_str).first():
        code_str = f'REF10-{_random_suffix(8)}'
    return DiscountCode(
        code_id          = generate_pk(),
        code             = code_str,
        code_type        = 'referral_friend',
        discount_percent = REF_DISCOUNT_PCT,
        for_user_id      = None,
        is_single_use    = True,
        max_uses         = 1,
        times_used       = 0,
        is_active        = True,
        expires_at       = datetime.now(timezone.utc) + timedelta(days=REF_CODE_EXPIRY),
        notes            = f'Referral friend code — referrer: {referred_by_vip.referral_code}',
    )


def generate_referral_code(user) -> str:
    """Generate a human-readable BAE-{Name}-{6char} referral code."""
    first  = (user.first_name or 'GUEST').upper()[:10]
    suffix = _random_suffix(6)
    code   = f'BAE-{first}-{suffix}'
    while VipCustomer.query.filter_by(referral_code=code).first():
        suffix = _random_suffix(6)
        code   = f'BAE-{first}-{suffix}'
    return code
