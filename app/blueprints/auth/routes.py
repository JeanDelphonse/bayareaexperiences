import os
import requests
from datetime import datetime, timezone, timedelta
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from app.blueprints.auth import auth_bp
from app.extensions import db, bcrypt, mail
from app.models import User
from app.utils import generate_pk, send_email


def get_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def verify_recaptcha(token):
    secret = current_app.config.get('RECAPTCHA_SECRET_KEY', '')
    if not secret:
        return True  # Skip in dev if not configured
    resp = requests.post(
        'https://www.google.com/recaptcha/api/siteverify',
        data={'secret': secret, 'response': token},
        timeout=5,
    )
    result = resp.json()
    return result.get('success') and result.get('score', 0) >= 0.5


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))
        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            flash('Welcome back!', 'success')
            return redirect(next_page or url_for('main.index'))
        flash('Invalid email or password.', 'danger')
    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        # reCAPTCHA v3
        recaptcha_token = request.form.get('g-recaptcha-response', '')
        if not verify_recaptcha(recaptcha_token):
            flash('reCAPTCHA verification failed. Please try again.', 'danger')
            return render_template('auth/register.html',
                                   recaptcha_site_key=current_app.config.get('RECAPTCHA_SITE_KEY', ''))

        first_name = request.form.get('first_name', '').strip()
        last_name  = request.form.get('last_name', '').strip()
        email      = request.form.get('email', '').strip().lower()
        password   = request.form.get('password', '')
        confirm    = request.form.get('confirm_password', '')

        if not all([first_name, last_name, email, password]):
            flash('All fields are required.', 'danger')
            return render_template('auth/register.html',
                                   recaptcha_site_key=current_app.config.get('RECAPTCHA_SITE_KEY', ''))
        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/register.html',
                                   recaptcha_site_key=current_app.config.get('RECAPTCHA_SITE_KEY', ''))
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return render_template('auth/register.html',
                                   recaptcha_site_key=current_app.config.get('RECAPTCHA_SITE_KEY', ''))
        if User.query.filter_by(email=email).first():
            flash('An account with that email already exists.', 'danger')
            return render_template('auth/register.html',
                                   recaptcha_site_key=current_app.config.get('RECAPTCHA_SITE_KEY', ''))

        pw_hash = bcrypt.generate_password_hash(password, rounds=12).decode('utf-8')
        user = User(
            user_id=generate_pk(),
            first_name=first_name,
            last_name=last_name,
            email=email,
            password_hash=pw_hash,
        )
        db.session.add(user)
        db.session.commit()

        # Send verification email
        token = get_serializer().dumps(email, salt='email-verify')
        verify_url = url_for('auth.verify_email', token=token, _external=True)
        try:
            send_email(
                mail,
                subject='Verify your Bay Area Experiences account',
                recipients=[email],
                body_html=render_template('auth/email_verify.html',
                                          user=user, verify_url=verify_url),
            )
            flash('Account created! Please check your email to verify your address.', 'success')
        except Exception:
            flash('Account created! (Email verification could not be sent — contact support.)', 'warning')

        return redirect(url_for('auth.login'))

    return render_template('auth/register.html',
                           recaptcha_site_key=current_app.config.get('RECAPTCHA_SITE_KEY', ''))


@auth_bp.route('/verify/<token>')
def verify_email(token):
    try:
        email = get_serializer().loads(token, salt='email-verify', max_age=86400)
    except (SignatureExpired, BadSignature):
        flash('The verification link is invalid or has expired.', 'danger')
        return redirect(url_for('auth.login'))
    user = User.query.filter_by(email=email).first_or_404()
    user.email_verified = True
    db.session.commit()
    flash('Email verified! You can now sign in.', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been signed out.', 'info')
    return redirect(url_for('main.index'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user  = User.query.filter_by(email=email).first()
        if user:
            token = get_serializer().dumps(email, salt='pw-reset')
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            try:
                send_email(
                    mail,
                    subject='Reset your Bay Area Experiences password',
                    recipients=[email],
                    body_html=render_template('auth/email_reset.html',
                                              user=user, reset_url=reset_url),
                )
            except Exception:
                pass
        # Always show the same message (security: don't reveal if email exists)
        flash('If that email is registered, a reset link has been sent.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        email = get_serializer().loads(token, salt='pw-reset', max_age=3600)
    except (SignatureExpired, BadSignature):
        flash('The reset link is invalid or has expired.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm_password', '')
        if password != confirm or len(password) < 8:
            flash('Passwords must match and be at least 8 characters.', 'danger')
            return render_template('auth/reset_password.html', token=token)
        user = User.query.filter_by(email=email).first_or_404()
        user.password_hash = bcrypt.generate_password_hash(password, rounds=12).decode('utf-8')
        db.session.commit()
        flash('Password updated! Please sign in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token)
