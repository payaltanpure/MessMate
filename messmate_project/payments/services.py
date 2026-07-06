import json
import os
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.core.exceptions import ImproperlyConfigured
import razorpay
from razorpay.errors import SignatureVerificationError
from student.models import Payment, WalletTransaction


def get_razorpay_client():
    key_id = getattr(settings, 'RAZORPAY_KEY_ID', None)
    key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', None)
    if not key_id or not key_secret:
        raise ImproperlyConfigured('Razorpay API keys are not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET.')
    return razorpay.Client(auth=(key_id, key_secret))


class RazorpayGateway:
    def __init__(self):
        self.client = get_razorpay_client()

    def create_order(self, amount, receipt, currency='INR', notes=None):
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


def verify_payment_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
    client = get_razorpay_client()
    params = {
        'razorpay_order_id': razorpay_order_id,
        'razorpay_payment_id': razorpay_payment_id,
        'razorpay_signature': razorpay_signature,
    }
    client.utility.verify_payment_signature(params)
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
    if reason:
        payment.gateway_transaction_id = reason[:200]
    payment.save()
    return payment


def refund_payment(payment: Payment, amount=None):
    if payment.status != 'success':
        return None
    if not payment.razorpay_payment_id:
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
