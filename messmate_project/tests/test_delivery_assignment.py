from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import DeliveryBoyProfile, User
from adminpanel.views import approve_delivery_boy
from core.delivery_views import assign_order_to_delivery_boy, set_delivery_boy_availability, transition_order_status
from student.models import Order
from vendor.models import Meal, Mess


class DeliveryAssignmentIntegrationTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username='studentassign',
            email='studentassign@example.com',
            password='StrongPass123',
            role='student',
        )
        self.vendor = User.objects.create_user(
            username='vendorassign',
            email='vendorassign@example.com',
            password='StrongPass123',
            role='vendor',
        )
        self.delivery_boy = User.objects.create_user(
            username='deliveryassign',
            email='deliveryassign@example.com',
            password='StrongPass123',
            role='delivery',
        )
        self.mess = Mess.objects.create(
            vendor=self.vendor,
            mess_name='Assignment Mess',
            address='Assignment Street',
            contact_number='2222222222',
            description='Assignment test mess',
            diet_type='veg',
            location_name='Campus',
            distance=1.0,
            monthly_price_both=Decimal('300.00'),
        )
        self.meal = Meal.objects.create(
            mess=self.mess,
            meal_type='lunch',
            name='Assignment Meal',
            menu_items='Rice, Dal',
            price=Decimal('120.00'),
            is_available=True,
        )

    def test_assign_order_to_delivery_boy_updates_order_state(self):
        order = Order.objects.create(
            student=self.student,
            mess=self.mess,
            total_amount=Decimal('120.00'),
            status='accepted',
        )

        assign_order_to_delivery_boy(order, self.delivery_boy, status='preparing')
        order.refresh_from_db()

        self.assertEqual(order.delivery_boy, self.delivery_boy)
        self.assertEqual(order.status, 'preparing')

    def test_assign_order_to_delivery_boy_marks_delivery_boy_busy(self):
        profile = DeliveryBoyProfile.objects.create(
            user=self.delivery_boy,
            verification_status='approved',
            availability_status='available',
        )
        order = Order.objects.create(
            student=self.student,
            mess=self.mess,
            total_amount=Decimal('120.00'),
            status='ready_for_pickup',
        )

        assign_order_to_delivery_boy(order, self.delivery_boy, status='assigned')
        profile.refresh_from_db()

        self.assertEqual(order.delivery_boy, self.delivery_boy)
        self.assertEqual(order.status, 'assigned')
        self.assertEqual(profile.availability_status, 'busy')

    def test_set_delivery_boy_availability_marks_boy_available_again(self):
        profile = DeliveryBoyProfile.objects.create(
            user=self.delivery_boy,
            verification_status='approved',
            availability_status='busy',
        )

        set_delivery_boy_availability(self.delivery_boy, True)
        profile.refresh_from_db()

        self.assertEqual(profile.availability_status, 'available')

    def test_delivery_status_update_allows_assigned_order_to_be_accepted(self):
        order = Order.objects.create(
            student=self.student,
            mess=self.mess,
            total_amount=Decimal('120.00'),
            status='assigned',
            delivery_boy=self.delivery_boy,
        )

        self.client.force_login(self.delivery_boy)
        response = self.client.post(reverse('update_delivery_status', args=[order.id, 'picked_up']), follow=True)

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, 'picked_up')

    def test_admin_approval_makes_delivery_boy_available_for_assignment(self):
        admin = User.objects.create_user(
            username='adminapproval',
            email='adminapproval@example.com',
            password='StrongPass123',
            role='admin',
            is_staff=True,
            is_superuser=True,
        )
        delivery_boy = User.objects.create_user(
            username='approvalboy',
            email='approvalboy@example.com',
            password='StrongPass123',
            role='delivery',
            is_active=True,
        )
        profile = DeliveryBoyProfile.objects.create(
            user=delivery_boy,
            verification_status='pending',
            availability_status='offline',
        )

        self.client.force_login(admin)
        response = self.client.post(reverse('adminpanel:approve_delivery_boy', args=[delivery_boy.id]), follow=True)

        self.assertEqual(response.status_code, 200)
        profile.refresh_from_db()
        self.assertEqual(profile.verification_status, 'approved')
        self.assertEqual(profile.availability_status, 'available')
        self.assertTrue(
            User.objects.filter(
                role='delivery',
                is_active=True,
                delivery_profile__verification_status='approved',
                delivery_profile__availability_status='available',
            ).exists()
        )

    def test_assign_delivery_boy_page_lists_active_delivery_boys_without_approval_filter(self):
        delivery_boy = User.objects.create_user(
            username='activeboy',
            email='activeboy@example.com',
            password='StrongPass123',
            role='delivery',
            is_active=True,
        )
        DeliveryBoyProfile.objects.create(
            user=delivery_boy,
            verification_status='pending',
            availability_status='offline',
        )
        order = Order.objects.create(
            student=self.student,
            mess=self.mess,
            total_amount=Decimal('120.00'),
            status='ready_for_pickup',
        )

        self.client.force_login(self.vendor)
        response = self.client.get(reverse('assign_delivery_boy', args=[order.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, delivery_boy.username)
        self.assertNotContains(response, 'No Approved Delivery Boys Available')

    def test_transition_order_status_supports_completed_state(self):
        order = Order.objects.create(
            student=self.student,
            mess=self.mess,
            total_amount=Decimal('120.00'),
            status='delivered',
        )

        transition_order_status(order, 'completed')
        order.refresh_from_db()

        self.assertEqual(order.status, 'completed')
