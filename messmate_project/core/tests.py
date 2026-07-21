from unittest.mock import patch

from django.conf import settings
from django.template import Context, Template
from django.test import SimpleTestCase, TestCase

from accounts.models import User
from core.email_services import send_email_message, send_registration_email
from core.weather_service import get_weather, get_weather_recommendations, get_weather_impact
from notifications.firebase_service import send_push_notification
from student.models import Notification


class EmailServiceTests(SimpleTestCase):
    def test_send_email_message_uses_demo_fallback_when_smtp_is_not_configured(self):
        with patch.dict('os.environ', {}, clear=True):
            with patch('core.email_services.send_mail') as mock_send_mail:
                result = send_email_message('Subject', 'Body', ['student@example.com'])

        self.assertTrue(result)
        mock_send_mail.assert_not_called()

    def test_send_registration_email_uses_user_email_when_configured(self):
        with patch.object(settings, 'EMAIL_HOST', 'smtp.example.com', create=True), \
             patch.object(settings, 'EMAIL_PORT', '587', create=True), \
             patch.object(settings, 'EMAIL_HOST_USER', 'demo@example.com', create=True), \
             patch.object(settings, 'EMAIL_HOST_PASSWORD', 'secret', create=True), \
             patch.object(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com', create=True):
            with patch('core.email_services.send_mail') as mock_send_mail:
                result = send_registration_email(
                    user_type='student',
                    user_name='Asha',
                    email='student@example.com',
                    verification_url='https://example.com/verify/1/'
                )

        self.assertTrue(result)
        mock_send_mail.assert_called_once()
        self.assertEqual(mock_send_mail.call_args[0][0], 'Welcome to MessMate')
        self.assertIn('Asha', mock_send_mail.call_args[0][1])


class WeatherServiceTests(SimpleTestCase):
    def test_get_weather_returns_demo_payload_without_api_key(self):
        with patch.object(settings, 'OPENWEATHER_API_KEY', '', create=True):
            result = get_weather('Bengaluru')

        self.assertTrue(result['available'])
        self.assertIn('demo', result['message'].lower())
        self.assertEqual(result['city'], 'Bengaluru')

    def test_get_weather_recommendations_and_impact_fallback_without_api_key(self):
        with patch.object(settings, 'OPENWEATHER_API_KEY', '', create=True):
            recommendations = get_weather_recommendations('Bengaluru', ['Soup', 'Biryani'])
            impact = get_weather_impact('Bengaluru')

        self.assertTrue(recommendations['available'])
        self.assertIn('demo', recommendations['message'].lower())
        self.assertTrue(impact['available'])
        self.assertIn('demo', impact['message'].lower())


class DemoModeIntegrationTests(TestCase):
    def test_demo_email_fallback_is_reported(self):
        with patch.object(settings, 'EMAIL_HOST', '', create=True), \
             patch.object(settings, 'EMAIL_PORT', '', create=True), \
             patch.object(settings, 'EMAIL_HOST_USER', '', create=True), \
             patch.object(settings, 'EMAIL_HOST_PASSWORD', '', create=True):
            result = send_email_message('Subject', 'Body', ['student@example.com'])

        self.assertTrue(result)

    def test_demo_push_fallback_creates_notification(self):
        user = User.objects.create_user(username='demo-push', email='demo-push@example.com', password='StrongPass123', role='student')
        result = send_push_notification(user, 'Hello', 'Body')

        self.assertTrue(result)
        self.assertTrue(Notification.objects.filter(user=user, title='Hello').exists())


class AnalyticsTemplateTests(SimpleTestCase):
    def test_ga_script_renders_only_when_measurement_id_is_configured(self):
        with patch.object(settings, 'GA_MEASUREMENT_ID', '', create=True):
            template = Template('{% if ga_measurement_id %}{{ ga_measurement_id }}{% endif %}')
            rendered = template.render(Context({'ga_measurement_id': ''}))

        self.assertEqual(rendered, '')

    def test_ga_script_renders_when_measurement_id_is_configured(self):
        template = Template('{% if ga_measurement_id %}{{ ga_measurement_id }}{% endif %}')
        rendered = template.render(Context({'ga_measurement_id': 'G-123456789'}))

        self.assertEqual(rendered, 'G-123456789')
