from decimal import Decimal
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from student.models import Complaint, Order, OrderItem, Subscription
from vendor.models import Meal, Mess


class ComplaintOrderSubscriptionTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username='studentops',
            email='studentops@example.com',
            password='StrongPass123',
            role='student',
        )
        self.vendor = User.objects.create_user(
            username='vendorops',
            email='vendorops@example.com',
            password='StrongPass123',
            role='vendor',
        )
        self.mess = Mess.objects.create(
            vendor=self.vendor,
            mess_name='Ops Mess',
            address='Ops Street',
            contact_number='3333333333',
            description='Operations test mess',
            diet_type='veg',
            location_name='Hostel',
            distance=1.5,
            monthly_price_both=Decimal('250.00'),
        )
        self.meal = Meal.objects.create(
            mess=self.mess,
            meal_type='lunch',
            name='Ops Meal',
            menu_items='Rice, Dal',
            price=Decimal('100.00'),
            is_available=True,
        )

    def test_complaint_can_be_created(self):
        complaint = Complaint.objects.create(
            student=self.student,
            mess=self.mess,
            category='wrong_order',
            description='Wrong meal delivered.',
            status='open',
        )
        self.assertEqual(complaint.status, 'open')

    def test_order_and_items_can_be_created(self):
        order = Order.objects.create(
            student=self.student,
            mess=self.mess,
            total_amount=Decimal('100.00'),
            status='pending',
        )
        OrderItem.objects.create(order=order, meal=self.meal, quantity=2, price=Decimal('100.00'))
        self.assertTrue(OrderItem.objects.filter(order=order).exists())

    def test_subscription_can_be_created(self):
        subscription = Subscription.objects.create(
            student=self.student,
            mess=self.mess,
            plan_type='both',
            start_date='2026-01-01',
            end_date='2026-01-31',
            price_paid='250.00',
            status='active',
            remaining_days=30,
            pause_remaining_days=30,
        )
        self.assertEqual(subscription.status, 'active')
