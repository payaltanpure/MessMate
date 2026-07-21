from django.test import TestCase
from django.urls import reverse

from accounts.models import DeliveryBoyProfile, User
from student.models import Complaint
from vendor.models import Mess


class AdminFlowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='adminflow',
            email='adminflow@example.com',
            password='StrongPass123',
            role='admin',
            is_staff=True,
            is_superuser=True,
        )
        self.student = User.objects.create_user(
            username='studentadmin',
            email='studentadmin@example.com',
            password='StrongPass123',
            role='student',
        )
        self.vendor = User.objects.create_user(
            username='vendoradmin',
            email='vendoradmin@example.com',
            password='StrongPass123',
            role='vendor',
        )
        self.mess = Mess.objects.create(
            vendor=self.vendor,
            mess_name='Admin Mess',
            address='Admin Street',
            contact_number='1111111111',
            description='Admin test mess',
            diet_type='veg',
            location_name='Hostel',
            distance=1.2,
        )
        self.complaint = Complaint.objects.create(
            student=self.student,
            mess=self.mess,
            category='food_quality',
            description='The meal was cold.',
            status='open',
        )

    def test_admin_dashboard_is_accessible(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('adminpanel:admin_dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_admin_can_view_complaints(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('adminpanel:manage_complaints'))
        self.assertEqual(response.status_code, 200)

    def test_admin_can_view_delivery_boys_management(self):
        delivery_boy = User.objects.create_user(
            username='deliveryadmin',
            email='deliveryadmin@example.com',
            password='StrongPass123',
            role='delivery',
        )
        DeliveryBoyProfile.objects.create(user=delivery_boy)

        self.client.force_login(self.admin)
        response = self.client.get(reverse('adminpanel:manage_delivery_boys'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Manage Delivery Boys')

    def test_home_page_shows_role_specific_login_options(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('login'))
        self.assertContains(response, reverse('adminpanel:admin_login'))

    def test_admin_login_allows_admin_role_only(self):
        response = self.client.post(
            reverse('adminpanel:admin_login'),
            {'username': 'adminflow', 'password': 'StrongPass123'},
            follow=True,
        )
        self.assertRedirects(response, reverse('adminpanel:admin_dashboard'))
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertEqual(response.wsgi_request.user.role, 'admin')

    def test_non_admin_user_is_redirected_back_to_admin_login(self):
        self.client.post(
            reverse('adminpanel:admin_login'),
            {'username': 'studentadmin', 'password': 'StrongPass123'},
            follow=True,
        )
        response = self.client.get(reverse('adminpanel:admin_dashboard'))
        self.assertRedirects(response, reverse('adminpanel:admin_login'))
