"""Traveler persona definitions and helpers for the Preference Engine."""

PERSONAS = [
    {
        'id':                 'history_buff',
        'label':              'History Buff',
        'emoji':              '\U0001F3DB',  # 🏛️
        'description':        'Dates, stories, and the people who built the Bay',
        'color_bg':           '#EFF4F9',
        'color_text':         '#1A3557',
        'claude_instruction': (
            'Emphasize historical context, founding stories, and cultural significance'
            ' at each stop. Reference specific dates, events, and personalities.'
        ),
    },
    {
        'id':                 'foodie',
        'label':              'Foodie',
        'emoji':              '\U0001F377',  # 🍷
        'description':        'Great bites, local producers, wine and craft beer',
        'color_bg':           '#FDF6EC',
        'color_text':         '#8B6419',
        'claude_instruction': (
            'Highlight food and drink culture. Suggest specific places to eat near'
            ' each stop, what to order, artisan producers, and any food events.'
        ),
    },
    {
        'id':                 'adventure_seeker',
        'label':              'Adventure Seeker',
        'emoji':              '\U0001F97E',  # 🥾
        'description':        'Trails, active stops, and jaw-dropping views',
        'color_bg':           '#E1F5EE',
        'color_text':         '#085041',
        'claude_instruction': (
            'Emphasize outdoor and active elements. Highlight trails, viewpoints'
            ' requiring a short hike, and any physical activities at each stop.'
        ),
    },
    {
        'id':                 'photographer',
        'label':              'Photographer',
        'emoji':              '\U0001F4F8',  # 📸
        'description':        'Best angles, golden hour, and hidden vantage points',
        'color_bg':           '#EEEDFE',
        'color_text':         '#26215C',
        'claude_instruction': (
            'Call out the best photo angles, ideal lighting times, unique vantage'
            ' points, and Instagram-worthy hidden spots at each location.'
        ),
    },
    {
        'id':                 'local_culture',
        'label':              'Local Culture Enthusiast',
        'emoji':              '\U0001F3A8',  # 🎨
        'description':        'Art, neighborhoods, murals, and authentic Bay life',
        'color_bg':           '#FEF3EC',
        'color_text':         '#7A3010',
        'claude_instruction': (
            'Focus on art, street murals, local neighborhoods, independent'
            ' businesses, and authentic Bay Area character over tourist landmarks.'
        ),
    },
    {
        'id':                 'relaxed_explorer',
        'label':              'Relaxed Explorer',
        'emoji':              '\u2601\uFE0F',  # ☁️
        'description':        'Scenic drives, slow stops, no rushing',
        'color_bg':           '#F2F5F8',
        'color_text':         '#3A4A5A',
        'claude_instruction': (
            'Keep the tone leisurely. Emphasize scenic drives, sit-down moments,'
            ' comfortable stops, and experiences with minimal walking.'
        ),
    },
    {
        'id':                 'celebration',
        'label':              'Celebrating Something',
        'emoji':              '\U0001F942',  # 🥂
        'description':        'Birthday, anniversary, bachelorette, or just life',
        'color_bg':           '#FBEAF0',
        'color_text':         '#4B1528',
        'claude_instruction': (
            'Acknowledge the occasion in the greeting and throughout. Suggest'
            ' at least one scenic celebratory photo moment. Warm, festive tone.'
        ),
    },
    {
        'id':                 'first_timer',
        'label':              'First-Timer in the Bay',
        'emoji':              '\u2B50',  # ⭐
        'description':        'The must-sees and why they matter',
        'color_bg':           '#E6F1FB',
        'color_text':         '#0C447C',
        'claude_instruction': (
            'Focus on iconic, must-see Bay Area experiences. Explain why each'
            ' landmark is significant. Prioritize "I can\'t believe I\'m here" moments.'
        ),
    },
]

INTEREST_TAG_GROUPS = {
    'Culinary':          ['Wine & Spirits', 'Craft Beer', 'Farm-to-Table',
                          'Street Food', 'Michelin Dining', 'Farmers Markets'],
    'Nature & Outdoors': ['Redwood Forests', 'Coastal Views', 'Bird Watching',
                          'Wildflowers', 'Beaches', 'Mountain Trails'],
    'History & Culture': ['Gold Rush Era', 'Beat Generation', 'Tech History',
                          'LGBTQ+ History', 'Immigrant Communities', 'Architecture'],
    'Entertainment':     ['Live Music', 'Comedy', 'Art Galleries',
                          'Street Performers', 'Night Life'],
    'Lifestyle':         ['Sustainability & Eco-Tourism', 'Wellness & Mindfulness',
                          'Pet-Friendly', 'Accessibility-Focused'],
    'Group Type':        ['Solo Traveler', 'Couple', 'Family with Kids',
                          'Friends Group', 'Corporate Team', 'Seniors'],
}


def get_persona_instructions(persona_ids: list) -> str:
    """Return a formatted instruction block for the Claude prompt."""
    if not persona_ids:
        return '  No personas selected — generate a balanced itinerary.'
    lines = []
    for pid in persona_ids:
        persona = next((p for p in PERSONAS if p['id'] == pid), None)
        if persona:
            lines.append(f'  - {persona["label"]}: {persona["claude_instruction"]}')
    return '\n'.join(lines) if lines else '  No personas selected.'
