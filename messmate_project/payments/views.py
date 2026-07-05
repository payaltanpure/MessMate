import random

from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from core.decorators import student_required, vendor_required
from student.models import Payment, WalletTransaction, Order, OrderItem, Cart, Subscription
from payments.services import RazorpayGateway, create_payment_record, finalize_successful_payment, process_refund


@require_POST
@student_required
def create_payment(request):
    # Minimal create payment endpoint for online checkout or wallet
    user = request.user
    amount = request.POST.get('amount')
    payment_method = request.POST.get('payment_method', 'online')
    order_id = request.POST.get('order_id')
    subscription_id = request.POST.get('subscription_id')
    try:
        amount_dec = Decimal(amount)
    except Exception:
        return JsonResponse({'error': 'Invalid amount'}, status=400)

    order = Order.objects.filter(id=order_id, student=user).first() if order_id else None
    subscription = Subscription.objects.filter(id=subscription_id, student=user).first() if subscription_id else None

    payment = create_payment_record(user=user, amount=amount_dec, payment_method=payment_method,
                                    gateway='razorpay', order=order, subscription=subscription)

    # Simulate gateway order creation
    gateway = RazorpayGateway()
    gw_order = gateway.create_order(amount=amount_dec, receipt=str(payment.payment_id))

    return JsonResponse({'payment_id': str(payment.payment_id), 'gateway_order': gw_order})


@require_POST
@student_required
def verify_payment(request):
    # Simulated verification endpoint
    payment_id = request.POST.get('payment_id')
    gateway_txn_id = request.POST.get('gateway_txn_id')
    signature = request.POST.get('signature')

    payment = get_object_or_404(Payment, payment_id=payment_id, user=request.user)
    gateway = RazorpayGateway()
    payload = gateway_txn_id or ''
    ok = gateway.verify_signature(payload, signature)
    if not ok:
        payment.status = 'failed'
        payment.save()
        return JsonResponse({'error': 'Signature verification failed'}, status=400)

    # finalize
    finalize_successful_payment(payment, gateway_txn_id)

    # Update related order/subscription states
    if payment.order:
        payment.order.status = 'pending' if payment.order.status == 'pending' else payment.order.status
        payment.order.save()
    if payment.subscription:
        payment.subscription.status = 'active'
        payment.subscription.save()

    return JsonResponse({'status': 'success'})


@student_required
def payment_page(request, payment_id):
    payment = get_object_or_404(Payment, payment_id=payment_id, user=request.user)
    if payment.status != 'pending':
        messages.info(request, 'This payment has already been processed.')
        if payment.status == 'success':
            return redirect('payment_success', payment_id=payment.payment_id)
        return redirect('payment_failed', payment_id=payment.payment_id)

    cart = Cart.objects.filter(student=request.user).first()
    order_items = []
    subscription = None
    if payment.subscription:
        subscription = payment.subscription
    elif cart:
        order_items = cart.items.all()
    return render(request, 'payments/payment_page.html', {
        'payment': payment,
        'order_items': order_items,
        'subscription': subscription,
    })


@require_POST
@student_required
def process_payment(request, payment_id):
    payment = get_object_or_404(Payment, payment_id=payment_id, user=request.user)
    if payment.status != 'pending':
        messages.error(request, 'Payment has already been processed.')
        if payment.status == 'success':
            return redirect('payment_success', payment_id=payment.payment_id)
        return redirect('payment_failed', payment_id=payment.payment_id)

    simulate_failure = request.POST.get('simulate_failure') == 'true'
    if simulate_failure:
        payment.status = 'failed'
        payment.save()
        return redirect('payment_failed', payment_id=payment.payment_id)

    cart = get_object_or_404(Cart, student=request.user)
    if not cart.items.exists():
        payment.status = 'failed'
        payment.save()
        messages.error(request, 'Cart is empty. Payment cannot be completed.')
        return redirect('payment_failed', payment_id=payment.payment_id)

    try:
        with transaction.atomic():
            if payment.subscription:
                sub = payment.subscription
                today = timezone.now().date()
                end = today + timezone.timedelta(days=30)
                sub.status = 'active'
                sub.start_date = today
                sub.end_date = end
                sub.price_paid = payment.amount
                sub.pause_date = None
                sub.pause_remaining_days = 30
                sub.save()

                payment.status = 'success'
                payment.save()
                WalletTransaction.objects.create(
                    user=request.user,
                    amount=payment.amount,
                    transaction_type='subscription_payment',
                    description=f"Subscription Payment for {sub.mess.mess_name}"
                )
            else:
                # Create order only after payment success
                mess = cart.items.first().meal.mess
                otp = f"{random.randint(100000, 999999)}"
                order = Order.objects.create(
                    student=request.user,
                    mess=mess,
                    total_amount=payment.amount,
                    status='pending',
                    delivery_otp=otp
                )
                for item in cart.items.all():
                    OrderItem.objects.create(
                        order=order,
                        meal=item.meal,
                        quantity=item.quantity,
                        price=item.meal.price
                    )
                cart.items.all().delete()

                # Finalize payment and transaction
                payment.order = order
                payment.status = 'success'
                payment.save()
                WalletTransaction.objects.create(
                    user=request.user,
                    amount=payment.amount,
                    transaction_type='order_payment',
                    description=f"Order Payment for Order #{order.id}"
                )
                order.save()
    except Exception:
        payment.status = 'failed'
        payment.save()
        return redirect('payment_failed', payment_id=payment.payment_id)

    return redirect('payment_success', payment_id=payment.payment_id)


@student_required
def payment_success(request, payment_id):
    payment = get_object_or_404(Payment, payment_id=payment_id, user=request.user)
    return render(request, 'payments/payment_success.html', {'payment': payment})


@student_required
def payment_failed(request, payment_id):
    payment = get_object_or_404(Payment, payment_id=payment_id, user=request.user)
    return render(request, 'payments/payment_failed.html', {'payment': payment})


@student_required
def payment_history(request):
    payments = Payment.objects.filter(user=request.user).order_by('-created_at')
    paginator = Paginator(payments, 20)
    page = request.GET.get('page')
    page_obj = paginator.get_page(page)
    return render(request, 'payments/history.html', {'payments': page_obj})


@require_POST
@student_required
def wallet_recharge(request):
    amount = request.POST.get('amount')
    try:
        amount_dec = Decimal(amount)
    except Exception:
        messages.error(request, 'Invalid amount')
        return redirect('wallet_detail')

    # Create payment and auto-finalize for recharge (simulation)
    payment = create_payment_record(user=request.user, amount=amount_dec, payment_method='online', gateway='razorpay')
    finalize_successful_payment(payment)
    # Credit to user's profile wallet
    profile = request.user.student_profile
    profile.wallet_balance = (profile.wallet_balance or Decimal('0')) + amount_dec
    profile.save()
    messages.success(request, f'Rs.{amount_dec} added to wallet')
    return redirect('wallet_detail')


@student_required
def transaction_history(request):
    txs = WalletTransaction.objects.filter(user=request.user).order_by('-created_at')
    paginator = Paginator(txs, 20)
    page = request.GET.get('page')
    page_obj = paginator.get_page(page)
    return render(request, 'payments/transactions.html', {'transactions': page_obj})


@vendor_required
def admin_refund(request, payment_id):
    # Vendor/admin can trigger refunds for successful payments related to their messes
    payment = get_object_or_404(Payment, payment_id=payment_id)
    if request.method == 'POST':
        process_refund(payment)
        messages.success(request, 'Refund processed')
    return redirect('vendor_earnings')
