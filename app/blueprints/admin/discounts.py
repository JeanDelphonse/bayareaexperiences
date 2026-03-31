"""Admin discount overview routes."""
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone

from flask import render_template, redirect, url_for, flash, request, jsonify
from app.blueprints.admin import admin_bp
from app.utils import admin_required
from app.extensions import db


@admin_bp.route('/discounts')
@admin_required
def admin_discounts():
    from app.models import Experience
    experiences = (Experience.query
                   .filter(Experience.discount_percent != None)  # noqa: E711
                   .order_by(Experience.sort_order)
                   .all())
    return render_template('admin/discounts.html', experiences=experiences)


@admin_bp.route('/discounts/<experience_id>/toggle', methods=['POST'])
@admin_required
def admin_discount_toggle(experience_id):
    from app.models import Experience
    exp = Experience.query.get_or_404(experience_id)
    if not exp.discount_percent or not exp.discounted_price:
        return jsonify({'error': 'No discount configured'}), 400
    exp.discount_active = not exp.discount_active
    db.session.commit()
    return jsonify({'active': exp.discount_active})


@admin_bp.route('/discounts/<experience_id>/clear', methods=['POST'])
@admin_required
def admin_discount_clear(experience_id):
    from app.models import Experience
    exp = Experience.query.get_or_404(experience_id)
    exp.discount_percent  = None
    exp.discounted_price  = None
    exp.discount_active   = False
    exp.discount_label    = None
    exp.discount_start    = None
    exp.discount_end      = None
    db.session.commit()
    flash(f'Discount cleared for "{exp.name}".', 'success')
    return redirect(url_for('admin.admin_discounts'))
