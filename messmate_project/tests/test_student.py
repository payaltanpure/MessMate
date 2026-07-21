from decimal import Decimal
from django.test import TestCase
from django.urls import reverse

from accounts.models import User, StudentProfile
from student.models import Cart, CartItem, Complaint, Order, OrderItem, Subscription, WalletTransaction
from payments.services import create_order_from_cart
from vendor.models import Meal, Mess


class StudentFlowTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username='studentflow',
            email='studentflow@example.com',
            password='StrongPass123',
            role='student',
        )
        StudentProfile.objects.create(user=self.student, wallet_balance=Decimal('500.00'))
        self.vendor = User.objects.create_user(
            username='vendorflow',
            email='vendorflow@example.com',
            password='StrongPass123',
            role='vendor',
        )
        self.mess = Mess.objects.create(
            vendor=self.vendor,
            mess_name='Flow Mess',
            address='Alpha Street',
            contact_number='5555555555',
            description='Test mess',
            diet_type='veg',
            location_name='Hostel',
            distance=1.5,
            monthly_price_both=Decimal('300.00'),
        )
        self.meal = Meal.objects.create(
            mess=self.mess,
            meal_type='lunch',
            name='Veg Rice',
            menu_items='Rice, Dal',
            price=Decimal('120.00'),
            is_available=True,
        )

    def test_student_dashboard_is_accessible(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('student_dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_student_can_add_to_cart(self):
        self.client.force_login(self.student)
        response = self.client.post(reverse('add_to_cart', args=[self.meal.id]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Cart.objects.filter(student=self.student).exists())

    def test_student_can_checkout_with_wallet(self):
        self.client.force_login(self.student)
        cart = Cart.objects.create(student=self.student)
        CartItem.objects.create(cart=cart, meal=self.meal, quantity=1)
        response = self.client.post(reverse('checkout_cart'), {'payment_method': 'wallet'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Order.objects.filter(student=self.student).exists())
        self.assertTrue(WalletTransaction.objects.filter(user=self.student).exists())

    def test_create_order_from_cart_creates_single_order(self):
        cart = Cart.objects.create(student=self.student)
        CartItem.objects.create(cart=cart, meal=self.meal, quantity=1)

        order = create_order_from_cart(self.student, cart, total_amount=Decimal('120.00'))

        self.assertEqual(Order.objects.filter(student=self.student).count(), 1)
        self.assertEqual(order.status, 'pending')
        self.assertEqual(order.mess, self.mess)
        self.assertFalse(CartItem.objects.filter(cart=cart).exists())

    def test_student_can_submit_complaint(self):
        self.client.force_login(self.student)
        response = self.client.post(reverse('submit_complaint'), {
            'description': 'The food tasted stale.',
            'mess_id': self.mess.id,
            'category': 'food_quality',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Complaint.objects.filter(student=self.student).exists())
