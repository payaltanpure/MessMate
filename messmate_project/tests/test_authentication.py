from django.test import TestCase
from django.urls import reverse

from accounts.models import User, StudentProfile


class AuthenticationTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username='studentone',
            email='student@example.com',
            password='StrongPass123',
            role='student',
        )
        StudentProfile.objects.create(user=self.student)

    def test_register_page_is_accessible(self):
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)

    def test_login_page_is_accessible(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)

    def test_student_can_login(self):
        response = self.client.post(reverse('login'), {
            'username': 'studentone',
            'password': 'StrongPass123',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Welcome back')

    def test_password_reset_page_is_accessible(self):
        response = self.client.get(reverse('forgot_password'))
        self.assertEqual(response.status_code, 200)
