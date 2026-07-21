from decimal import Decimal
from django.test import TestCase

from accounts.models import User, StudentProfile
from student.models import WalletTransaction


class WalletTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username='walletstudent',
            email='walletstudent@example.com',
            password='StrongPass123',
            role='student',
        )
        self.profile = StudentProfile.objects.create(user=self.student, wallet_balance=Decimal('100.00'))

    def test_wallet_transaction_can_be_created(self):
        WalletTransaction.objects.create(
            user=self.student,
            amount=Decimal('50.00'),
            transaction_type='credit',
            description='Wallet recharge',
        )
        self.assertTrue(WalletTransaction.objects.filter(user=self.student).exists())
