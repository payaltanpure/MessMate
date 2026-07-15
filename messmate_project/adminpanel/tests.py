from django.test import TestCase
from django.urls import reverse

from accounts.models import User
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
