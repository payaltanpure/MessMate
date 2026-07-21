from django.test import SimpleTestCase, override_settings

from core.maps_service import build_directions_url, build_open_maps_url, get_maps_config, get_mess_map_data


class MapsServiceTests(SimpleTestCase):
    def test_returns_placeholder_when_api_key_missing(self):
        with override_settings(GOOGLE_MAPS_API_KEY=''):
            config = get_maps_config()
            self.assertFalse(config['enabled'])
            self.assertIn('unavailable', config['placeholder_message'].lower())

    def test_builds_urls_for_mess(self):
        class DummyMess:
            mess_name = 'Annapurna Mess'
            address = 'Main Road'
            location_name = 'North Campus'
            latitude = 12.34
            longitude = 56.78

        mess = DummyMess()
        data = get_mess_map_data(mess)
        self.assertEqual(data['latitude'], 12.34)
        self.assertEqual(data['longitude'], 56.78)
        self.assertIn('google.com/maps/dir', build_directions_url(mess))
        self.assertIn('google.com/maps/search', build_open_maps_url(mess))
