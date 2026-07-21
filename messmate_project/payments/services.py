import json
import os
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.core.exceptions import ImproperlyConfigured
import razorpay
from razorpay.errors import SignatureVerificationError
from student.models import Payment, WalletTransaction, Order, OrderItem, Cart
from core.integration_fallbacks import is_demo_mode_enabled, log_demo_fallback

# Razorpay Integration (Temporarily Disabled)
SIMULATED_PAYMENT_FLOW_ENABLED = True


def get_razorpay_client():
    key_id = getattr(settings, 'RAZORPAY_KEY_ID', None)
    key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', None)
    if SIMULATED_PAYMENT_FLOW_ENABLED or is_demo_mode_enabled('razorpay', [key_id, key_secret]):
        log_demo_fallback('razorpay', 'Razorpay keys missing', 'simulate payment success and generate demo transaction IDs')
        return None
    if not key_id or not key_secret:
        raise ImproperlyConfigured('Razorpay API keys are not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET.')
    return razorpay.Client(auth=(key_id, key_secret))


class RazorpayGateway:
    def __init__(self):
        self.client = get_razorpay_client()

    def create_order(self, amount, receipt, currency='INR', notes=None):
        if SIMULATED_PAYMENT_FLOW_ENABLED:
            return {
                'id': f'simulated-order-{receipt}',
                'amount': int(Decimal(amount) * 100),
                'currency': currency,
                'status': 'created',
            }
        amount_paise = int(Decimal(amount) * 100)
        order_data = {
            'amount': amount_paise,
            'currency': currency,
            'receipt': receipt,
            'payment_capture': 1,
        }
        if notes:
            order_data['notes'] = notes
        return self.client.order.create(order_data)


def create_razorpay_order(amount, receipt, currency='INR', notes=None):
    # Razorpay Integration (Temporarily Disabled)
    if SIMULATED_PAYMENT_FLOW_ENABLED or is_demo_mode_enabled('razorpay', [getattr(settings, 'RAZORPAY_KEY_ID', None), getattr(settings, 'RAZORPAY_KEY_SECRET', None)]):
        return f'simulated-order-{receipt}'
    client = get_razorpay_client()
    amount_paise = int(Decimal(amount) * 100)
    order_data = {
        'amount': amount_paise,
        'currency': currency,
        'receipt': receipt,
        'payment_capture': 1,
    }
    if notes:
        order_data['notes'] = notes

    razorpay_order = client.order.create(order_data)
    return razorpay_order.get('id')


def verify_payment_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature, expected_amount=None):
    # Razorpay Integration (Temporarily Disabled)
    if SIMULATED_PAYMENT_FLOW_ENABLED or is_demo_mode_enabled('razorpay', [getattr(settings, 'RAZORPAY_KEY_ID', None), getattr(settings, 'RAZORPAY_KEY_SECRET', None)]):
        return True
    client = get_razorpay_client()
    params = {
        'razorpay_order_id': razorpay_order_id,
        'razorpay_payment_id': razorpay_payment_id,
        'razorpay_signature': razorpay_signature,
    }
    try:
        client.utility.verify_payment_signature(params)
    except SignatureVerificationError:
        raise ValueError('Payment signature verification failed.')

    if expected_amount is not None:
        payment_data = client.payment.fetch(razorpay_payment_id)
        
        if int(Decimal(expected_amount) * 100) != int(payment_data.get('amount', 0)):
            raise ValueError('Payment amount mismatch.')

    return True


def mark_payment_success(payment: Payment, razorpay_order_id=None, razorpay_payment_id=None,
                         razorpay_signature=None, gateway_transaction_id=None):
    payment.status = 'success'
    if razorpay_order_id:
        payment.razorpay_order_id = razorpay_order_id
    if razorpay_payment_id:
        payment.razorpay_payment_id = razorpay_payment_id
    if razorpay_signature:
        payment.razorpay_signature = razorpay_signature
    if gateway_transaction_id:
        payment.gateway_transaction_id = gateway_transaction_id
    payment.save()
    return payment


def mark_payment_failed(payment: Payment, reason=None):
    payment.status = 'failed'
    payment.save()
    return payment


def mark_payment_cancelled(payment: Payment, reason=None):
    payment.status = 'cancelled'
    payment.save()
    return payment


def refund_payment(payment: Payment, amount=None):
    if not payment.razorpay_payment_id:
        return None

    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(id=payment.id)
        if payment.status != 'success':
            return None

        client = get_razorpay_client()
        refund_amount = int(Decimal(amount or payment.amount) * 100)
        response = client.payment.refund(payment.razorpay_payment_id, {'amount': refund_amount})
        payment.status = 'refunded'
        payment.save()
        WalletTransaction.objects.create(
            user=payment.user,
            amount=Decimal(amount or payment.amount),
            transaction_type='refund',
            description=f"Refund for Payment {payment.payment_id}"
        )
        return response


def get_payment_status(payment_id):
    client = get_razorpay_client()
    return client.payment.fetch(payment_id)


def create_payment_record(user, amount, payment_method='online', gateway='razorpay',
                          gateway_txn_id=None, order=None, subscription=None):
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


def create_order_from_cart(student, cart, total_amount, delivery_otp=None):
    if not isinstance(cart, Cart):
        cart = Cart.objects.select_related('student').get(student=student)

    if not cart.items.exists():
        raise ValueError('Cart is empty.')

    mess = cart.items.first().meal.mess
    otp = delivery_otp or f"{os.urandom(2).hex()}"

    with transaction.atomic():
        order = Order.objects.create(
            student=student,
            mess=mess,
            total_amount=Decimal(total_amount),
            status='pending',
            delivery_otp=otp,
        )
        for item in cart.items.select_related('meal').all():
            OrderItem.objects.create(
                order=order,
                meal=item.meal,
                quantity=item.quantity,
                price=item.meal.price,
            )
        cart.items.all().delete()

    return order
