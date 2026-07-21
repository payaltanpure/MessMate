from django.test import TestCase

from accounts.models import User
from notifications.firebase_service import save_fcm_token, send_push_notification


class FirebasePushNotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='pushuser',
            email='push@example.com',
            password='StrongPass123',
            role='student',
        )

    def test_fcm_token_can_be_saved_and_push_skips_safely(self):
        saved = save_fcm_token(self.user, 'test-token')
        self.assertTrue(saved)
        self.assertEqual(self.user.fcm_token, 'test-token')

        result = send_push_notification(self.user, 'Hello', 'Body')
        self.assertFalse(result)
