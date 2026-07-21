from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from vendor.models import Meal, Mess


class VendorFlowTests(TestCase):
    def setUp(self):
        self.vendor = User.objects.create_user(
            username='vendoralpha',
            email='vendoralpha@example.com',
            password='StrongPass123',
            role='vendor',
        )
        self.mess = Mess.objects.create(
            vendor=self.vendor,
            mess_name='Vendor Mess',
            address='Main Road',
            contact_number='1234567890',
            description='Vendor test mess',
            diet_type='both',
            location_name='Hostel',
            distance=2.0,
        )

    def test_vendor_dashboard_is_accessible(self):
        self.client.force_login(self.vendor)
        response = self.client.get(reverse('vendor_dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_vendor_can_create_meal(self):
        self.client.force_login(self.vendor)
        response = self.client.post(
            reverse('add_meal', args=[self.mess.id]),
            {
                'meal_type': 'lunch',
                'name': 'Special Rice',
                'menu_items': 'Rice, Dal',
                'price': '90.00',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Meal.objects.filter(name='Special Rice').exists())
