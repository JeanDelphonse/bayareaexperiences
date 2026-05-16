VEHICLE_DISPLAY = {
    'cadillac_escalade':  'Cadillac Escalade',
    'lincoln_navigator':  'Lincoln Navigator',
    'mercedes_sprinter':  'Mercedes-Benz Sprinter',
    'mercedes_s_class':   'Mercedes-Benz S-Class',
    'bmw_7_series':       'BMW 7 Series',
    'luxury_suv_custom':  None,  # use experience.luxury_vehicle_custom
}

VEHICLE_CHOICES = [
    ('cadillac_escalade',  'Cadillac Escalade'),
    ('lincoln_navigator',  'Lincoln Navigator'),
    ('mercedes_sprinter',  'Mercedes-Benz Sprinter (Executive Van)'),
    ('mercedes_s_class',   'Mercedes-Benz S-Class'),
    ('bmw_7_series',       'BMW 7 Series'),
    ('luxury_suv_custom',  'Luxury Vehicle (Custom — specify below)'),
]


def get_vehicle_display(experience):
    """Return the display name for a luxury experience vehicle."""
    if not experience.is_premium:
        return None
    if experience.luxury_vehicle_type == 'luxury_suv_custom':
        return experience.luxury_vehicle_custom or 'Luxury Vehicle'
    return VEHICLE_DISPLAY.get(experience.luxury_vehicle_type, 'Luxury Vehicle')
