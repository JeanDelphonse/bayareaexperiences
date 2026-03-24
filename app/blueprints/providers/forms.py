"""Provider forms — application, experience listing, profile."""
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileSize
from wtforms import (StringField, TextAreaField, SelectField, SelectMultipleField,
                     IntegerField, DecimalField, BooleanField, SubmitField)
from wtforms.validators import DataRequired, Email, Length, Optional, NumberRange, URL

PICKUP_CITIES = [
    ('San Francisco, CA', 'San Francisco, CA'),
    ('San Jose, CA',      'San Jose, CA'),
    ('Santa Cruz, CA',    'Santa Cruz, CA'),
    ('Monterey, CA',      'Monterey, CA'),
]

CATEGORIES = [
    ('', '— Select category —'),
    ('Sightseeing',     'Sightseeing'),
    ('Wine & Spirits',  'Wine & Spirits'),
    ('Food & Culinary', 'Food & Culinary'),
    ('Adventure',       'Adventure'),
    ('Cultural',        'Cultural'),
    ('Photography',     'Photography'),
    ('Transportation',  'Transportation'),
    ('Corporate',       'Corporate'),
    ('Celebration',     'Celebration'),
    ('Other',           'Other'),
]

ADVANCE_DAYS = [
    ('1', '1 day'),
    ('2', '2 days'),
    ('3', '3 days'),
    ('5', '5 days'),
    ('7', '7 days'),
]

CANCELLATION_POLICIES = [
    ('flexible', 'Flexible — Full refund if cancelled 48+ hours before'),
    ('moderate', 'Moderate — 50% refund if cancelled 5+ days before'),
    ('strict',   'Strict — No refund'),
]


class ProviderApplicationForm(FlaskForm):
    business_name     = StringField('Business / Provider Name',
                                    validators=[DataRequired(), Length(min=2, max=200)])
    phone             = StringField('Phone Number',
                                    validators=[DataRequired(), Length(max=30)])
    bio               = TextAreaField('Tell us about yourself and your experience',
                                      validators=[DataRequired(), Length(min=50, max=2000)])
    experience_types  = StringField('What types of experiences do you offer?',
                                    validators=[DataRequired(), Length(max=500)])
    years_experience  = IntegerField('Years of experience in tourism/hospitality',
                                     validators=[DataRequired(), NumberRange(min=0, max=50)])
    service_cities    = SelectMultipleField('Cities you serve',
                                            choices=PICKUP_CITIES,
                                            validators=[DataRequired()])
    website           = StringField('Website (optional)',
                                    validators=[Optional(), URL(), Length(max=300)])
    instagram         = StringField('Instagram handle (optional)',
                                    validators=[Optional(), Length(max=100)])
    languages_spoken  = StringField('Languages spoken (e.g. English, Spanish)',
                                    validators=[Optional(), Length(max=200)])
    why_join          = TextAreaField('Why do you want to join Bay Area Experiences?',
                                      validators=[DataRequired(), Length(min=30, max=1000)])
    submit            = SubmitField('Submit Application')


class ProviderExperienceForm(FlaskForm):
    name                 = StringField('Experience Title',
                                       validators=[DataRequired(), Length(max=80)])
    short_description    = StringField('Short Description (shown on cards)',
                                       validators=[DataRequired(), Length(max=200)])
    description          = TextAreaField('Full Description',
                                          validators=[DataRequired(), Length(min=20)])
    category             = SelectField('Category', choices=CATEGORIES,
                                       validators=[DataRequired()])
    duration_hours       = DecimalField('Duration (hours)', places=1,
                                         validators=[DataRequired(), NumberRange(min=0.5, max=12)])
    price                = DecimalField('Price per booking ($)', places=2,
                                         validators=[DataRequired(), NumberRange(min=25, max=5000)])
    max_guests           = IntegerField('Max guests', default=4,
                                         validators=[DataRequired(), NumberRange(min=1, max=8)])
    pickup_cities        = SelectMultipleField('Pickup cities', choices=PICKUP_CITIES,
                                               validators=[Optional()])
    inclusions           = TextAreaField('What is included',
                                          validators=[DataRequired(), Length(max=1000)])
    what_to_bring        = TextAreaField('What guests should bring (optional)',
                                          validators=[Optional(), Length(max=500)])
    cancellation_policy  = SelectField('Cancellation policy',
                                       choices=CANCELLATION_POLICIES,
                                       validators=[DataRequired()])
    advance_booking_days = SelectField('Advance booking required', choices=ADVANCE_DAYS,
                                       default='1', validators=[DataRequired()])
    photo_url            = StringField('Main photo filename',
                                       validators=[Optional(), Length(max=200)])
    is_active            = BooleanField('Listing is active', default=True)
    submit               = SubmitField('Save Experience')


class ProviderProfileForm(FlaskForm):
    business_name    = StringField('Business Name',
                                   validators=[DataRequired(), Length(max=200)])
    bio              = TextAreaField('Bio',
                                     validators=[DataRequired(), Length(min=50, max=2000)])
    website          = StringField('Website', validators=[Optional(), URL(), Length(max=300)])
    instagram        = StringField('Instagram handle', validators=[Optional(), Length(max=100)])
    languages_spoken = StringField('Languages spoken', validators=[Optional(), Length(max=200)])
    years_experience = IntegerField('Years of experience',
                                    validators=[Optional(), NumberRange(min=0, max=50)])
    submit           = SubmitField('Save Profile')


class ProviderDocUploadForm(FlaskForm):
    doc_type   = SelectField('Document type', choices=[
        ('government_id',       'Government ID'),
        ('business_license',    'Business License'),
        ('insurance',           'Liability Insurance Certificate'),
        ('vehicle_registration','Vehicle Registration'),
        ('background_check',    'Background Check'),
    ], validators=[DataRequired()])
    expires_at = StringField('Expiry date (YYYY-MM-DD, if applicable)',
                             validators=[Optional()])
    doc_file   = FileField('Document file (PDF, JPG, PNG — max 10 MB)',
                           validators=[
                               DataRequired(),
                               FileAllowed(['pdf', 'jpg', 'jpeg', 'png'], 'PDF, JPG, PNG only'),
                               FileSize(max_size=10 * 1024 * 1024),
                           ])
    submit     = SubmitField('Upload Document')
