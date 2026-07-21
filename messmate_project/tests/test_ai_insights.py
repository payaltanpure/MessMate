from decimal import Decimal
from django.test import TestCase

from accounts.models import User
from core.ai_services import get_ai_insights
from student.models import Order, OrderItem
from vendor.models import Meal, Mess


class AIInsightsServiceTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username='insightstudent',
            email='insightstudent@example.com',
            password='StrongPass123',
            role='student',
        )
        self.vendor = User.objects.create_user(
            username='insightvendor',
            email='insightvendor@example.com',
            password='StrongPass123',
            role='vendor',
        )
        self.mess = Mess.objects.create(
            vendor=self.vendor,
            mess_name='Insight Mess',
            address='Insight Street',
            contact_number='4444444444',
            description='Insight test',
            diet_type='veg',
            location_name='Hostel',
            distance=1.0,
        )
        self.meal = Meal.objects.create(
            mess=self.mess,
            meal_type='lunch',
            name='Paneer Rice',
            menu_items='Paneer, Rice',
            price=Decimal('95.00'),
            is_available=True,
        )
        self.order = Order.objects.create(
            student=self.student,
            mess=self.mess,
            total_amount=Decimal('95.00'),
            status='delivered',
        )
        OrderItem.objects.create(order=self.order, meal=self.meal, quantity=1, price=Decimal('95.00'))

    def test_student_insights_payload_contains_expected_sections(self):
        payload = get_ai_insights('student', self.student)
        self.assertIn('spending', payload)
        self.assertIn('favorite_meals', payload)
        self.assertIn('summary', payload)

    def test_vendor_insights_payload_contains_expected_sections(self):
        payload = get_ai_insights('vendor', self.vendor)
        self.assertIn('sales', payload)
        self.assertIn('popular_meals', payload)
        self.assertIn('summary', payload)

    def test_admin_insights_payload_contains_expected_sections(self):
        payload = get_ai_insights('admin')
        self.assertIn('platform', payload)
        self.assertIn('complaints', payload)
        self.assertIn('summary', payload)
