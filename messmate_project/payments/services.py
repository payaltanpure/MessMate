import hashlib
import hmac
from decimal import Decimal
from django.conf import settings
from student.models import Payment, WalletTransaction


class PaymentGatewayBase:
    def create_order(self, amount, currency='INR', receipt=None):
        raise NotImplementedError()

    def verify_signature(self, data, signature):
        raise NotImplementedError()


class RazorpayGateway(PaymentGatewayBase):
    def __init__(self, key_id=None, key_secret=None):
        self.key_id = key_id or getattr(settings, 'RAZORPAY_KEY_ID', None)
        self.key_secret = key_secret or getattr(settings, 'RAZORPAY_KEY_SECRET', None)

    def create_order(self, amount, currency='INR', receipt=None):
        # Placeholder: in production call razorpay.Client(order creation)
        # return dict with order_id and amount
        mock_order_id = f"rp_order_mock_{int(Decimal(amount))}_{receipt or 'r'}"
        return {'id': mock_order_id, 'amount': amount, 'currency': currency}

    def verify_signature(self, payload, signature):
        # Simulated verification using HMAC if key_secret available
        if not self.key_secret:
            return True
        msg = payload.encode('utf-8')
        secret = self.key_secret.encode('utf-8')
        expected = hmac.new(secret, msg, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


def create_payment_record(user, amount, payment_method='online', gateway='razorpay',
                          gateway_txn_id=None, order=None, subscription=None):
    # Prevent duplicate gateway_transaction_id
    if gateway_txn_id and Payment.objects.filter(gateway_transaction_id=gateway_txn_id).exists():
        return Payment.objects.get(gateway_transaction_id=gateway_txn_id)

    p = Payment.objects.create(
        user=user,
        amount=Decimal(amount),
        payment_method=payment_method,
        payment_gateway=gateway,
        gateway_transaction_id=gateway_txn_id,
        order=order,
        subscription=subscription,
        status='pending'
    )
    return p


def finalize_successful_payment(payment: Payment, gateway_txn_id=None):
    payment.status = 'success'
    if gateway_txn_id:
        payment.gateway_transaction_id = gateway_txn_id
    payment.save()

    # Create wallet transaction record mapping type
    if payment.order:
        WalletTransaction.objects.create(
            user=payment.user,
            amount=payment.amount,
            transaction_type='order_payment',
            description=f"Order Payment #{payment.order.id}"
        )
    elif payment.subscription:
        WalletTransaction.objects.create(
            user=payment.user,
            amount=payment.amount,
            transaction_type='subscription_payment',
            description=f"Subscription Payment #{payment.subscription.id}"
        )
    else:
        WalletTransaction.objects.create(
            user=payment.user,
            amount=payment.amount,
            transaction_type='recharge',
            description=f"Wallet Recharge"
        )

    return payment


def process_refund(payment: Payment, amount=None):
    # Mark payment refunded and add wallet refund transaction
    if payment.status != 'success':
        return None
    payment.status = 'refunded'
    payment.save()
    refund_amount = Decimal(amount) if amount else payment.amount
    WalletTransaction.objects.create(
        user=payment.user,
        amount=refund_amount,
        transaction_type='refund',
        description=f"Refund for Payment {payment.payment_id}"
    )
    return payment
