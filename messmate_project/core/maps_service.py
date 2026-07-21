from urllib.parse import quote

from django.conf import settings

from core.integration_fallbacks import is_demo_mode_enabled, log_demo_fallback

DEFAULT_CENTER = {
    'lat': 12.9716,
    'lng': 77.5946,
}


def get_maps_config(api_key=None):
    """Return a shared maps configuration object for templates and view logic."""
    key = str(api_key or getattr(settings, 'GOOGLE_MAPS_API_KEY', '') or '').strip()
    demo_mode = is_demo_mode_enabled('maps', [key])
    if demo_mode:
        log_demo_fallback('maps', 'Google Maps API key missing', 'show stored coordinates and preview card')
    return {
        'api_key': key,
        'enabled': bool(key) and not demo_mode,
        'placeholder_message': 'Map Preview (Demo Mode)',
        'default_center': DEFAULT_CENTER,
        'demo_mode': demo_mode,
    }


def get_mess_map_data(mess):
    """Return a normalized coordinate payload for a mess object."""
    latitude = getattr(mess, 'latitude', None)
    longitude = getattr(mess, 'longitude', None)
    if latitude is None or longitude is None:
        return {
            'latitude': DEFAULT_CENTER['lat'],
            'longitude': DEFAULT_CENTER['lng'],
            'has_coordinates': False,
        }
    return {
        'latitude': float(latitude),
        'longitude': float(longitude),
        'has_coordinates': True,
    }


def build_directions_url(mess):
    """Build a Google Maps directions URL for a mess."""
    destination = ' '.join(filter(None, [getattr(mess, 'address', None), getattr(mess, 'location_name', None), getattr(mess, 'mess_name', None)]))
    destination = destination.strip() or 'mess location'
    return f'https://www.google.com/maps/dir/?api=1&destination={quote(destination)}'


def build_open_maps_url(mess):
    """Build a Google Maps search URL for a mess."""
    query = ' '.join(filter(None, [getattr(mess, 'mess_name', None), getattr(mess, 'address', None), getattr(mess, 'location_name', None)]))
    query = query.strip() or 'hostel mess'
    return f'https://www.google.com/maps/search/?api=1&query={quote(query)}'
