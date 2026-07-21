from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from student.models import Complaint, Subscription
from vendor.models import Meal, Mess


class AdminMealManagementTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username='adminuser',
            email='admin@example.com',
            password='StrongPass123',
            role='admin',
            is_staff=True,
            is_superuser=True,
        )
        self.vendor_user = User.objects.create_user(
            username='vendoruser',
            email='vendor@example.com',
            password='StrongPass123',
            role='vendor',
        )
        self.mess = Mess.objects.create(
            vendor=self.vendor_user,
            mess_name='Test Mess',
            address='123 Main St',
            contact_number='9999999999',
            description='Test description',
            diet_type='veg',
            location_name='Hostel Campus',
            distance=1.2,
        )
        self.meal = Meal.objects.create(
            mess=self.mess,
            meal_type='lunch',
            name='Paneer Rice',
            menu_items='Paneer, Rice, Dal',
            price='120.00',
            is_available=True,
        )
        self.student_user = User.objects.create_user(
            username='studentuser',
            email='student@example.com',
            password='StrongPass123',
            role='student',
        )
        self.subscription = Subscription.objects.create(
            student=self.student_user,
            mess=self.mess,
            plan_type='lunch',
            start_date='2026-01-01',
            end_date='2026-01-31',
            price_paid='300.00',
            status='active',
            remaining_days=30,
            pause_remaining_days=30,
        )
        self.complaint = Complaint.objects.create(
            student=self.student_user,
            mess=self.mess,
            category='food_quality',
            description='Food was cold at dinner.',
            status='open',
        )

    def test_admin_can_view_meals_page(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('adminpanel:manage_meals'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Paneer Rice')

    def test_admin_can_view_meal_detail_page(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('adminpanel:meal_detail', args=[self.meal.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Paneer Rice')

    def test_admin_can_view_meals_page_via_admin_panel_prefix(self):
        self.client.force_login(self.admin_user)
        response = self.client.get('/admin-panel/meals/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Paneer Rice')

    def test_admin_can_view_subscriptions_page(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('adminpanel:manage_subscriptions'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Subscription')

    def test_admin_can_view_subscription_detail_page(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('adminpanel:subscription_detail', args=[self.subscription.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.subscription.mess.mess_name)

    def test_admin_can_view_complaints_page(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('adminpanel:manage_complaints'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Food was cold at dinner.')

    def test_admin_can_view_complaint_detail_page(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('adminpanel:complaint_detail', args=[self.complaint.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Food was cold at dinner.')

    def test_admin_can_view_analytics_page(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('adminpanel:analytics_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Analytics & Reports')

    def test_admin_can_view_ai_insights_page(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('adminpanel:ai_insights'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'AI Insights')
