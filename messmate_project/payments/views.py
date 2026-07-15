import random
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.urls import reverse
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from razorpay.errors import SignatureVerificationError
from core.decorators import student_required, vendor_required
from accounts.models import StudentProfile
from student.models import Payment, WalletTransaction, Order, OrderItem, Cart, Subscription, Notification
from vendor.models import Mess
from payments.services import (
    RazorpayGateway,
    get_razorpay_client,
    create_payment_record,
    create_razorpay_order,
    verify_payment_signature,
    mark_payment_success,
    mark_payment_failed,
    mark_payment_cancelled,
    refund_payment
)

logger = logging.getLogger(__name__)


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
    payment_id = request.POST.get('payment_id')
    razorpay_order_id = request.POST.get('razorpay_order_id') or request.POST.get('order_id')
    razorpay_payment_id = request.POST.get('razorpay_payment_id')
    razorpay_signature = request.POST.get('razorpay_signature')
    simulate_payment = request.POST.get('simulate_payment') == 'true'

    if not simulate_payment and not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
        return JsonResponse({'error': 'Missing payment verification data.'}, status=400)

    payment = None
    if payment_id:
        payment = Payment.objects.filter(payment_id=payment_id, user=request.user).first()
    if not payment and razorpay_order_id:
        payment = Payment.objects.filter(user=request.user, razorpay_order_id=razorpay_order_id).first()
    if not payment and razorpay_payment_id:
        payment = Payment.objects.filter(user=request.user, razorpay_payment_id=razorpay_payment_id).first()
    if not payment:
        return JsonResponse({'error': 'Payment record not found.'}, status=404)

    if payment.status != 'pending':
        return JsonResponse({'error': 'Payment already processed.'}, status=400)

    if not razorpay_order_id:
        razorpay_order_id = f'simulated-order-{payment.payment_id}'
    if not razorpay_payment_id:
        razorpay_payment_id = f'simulated-payment-{payment.payment_id}'
    if not razorpay_signature:
        razorpay_signature = 'simulated-signature'

    try:
        verify_payment_signature(
            razorpay_order_id,
            razorpay_payment_id,
            razorpay_signature,
            expected_amount=payment.amount
        )
    except (SignatureVerificationError, ValueError, Exception) as exc:
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(id=payment.id)
            if payment.status == 'pending':
                mark_payment_failed(payment, reason=str(exc))
        if isinstance(exc, SignatureVerificationError):
            return JsonResponse({'error': 'Signature verification failed.', 'details': str(exc)}, status=400)
        elif isinstance(exc, ValueError):
            return JsonResponse({'error': 'Payment validation failed.', 'details': str(exc)}, status=400)
        else:
            return JsonResponse({'error': 'Verification error.', 'details': str(exc)}, status=500)

    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(id=payment.id)
        if payment.status != 'pending':
            return JsonResponse({'error': 'Payment already processed during verification.'}, status=400)
            
        purpose = request.POST.get('purpose') or request.session.pop(f'payment_purpose_{payment.payment_id}', None)
        notes = {}

        if purpose == 'subscription_checkout':
            mess_id = request.POST.get('mess_id') or request.session.get(f'payment_mess_id_{payment.payment_id}')
            plan_type = request.POST.get('plan_type') or request.session.get(f'payment_plan_type_{payment.payment_id}')
            if not mess_id or not plan_type:
                raise ValueError('Subscription metadata missing from payment.')

            mess = Mess.objects.filter(id=mess_id).first()
            if not mess:
                raise ValueError('Mess not found for subscription.')

            # Cancel any existing active subscription for this mess
            Subscription.objects.filter(student=request.user, mess=mess, status='active').update(status='expired')

            today = timezone.now().date()
            end = today + timezone.timedelta(days=30)
            sub = Subscription.objects.create(
                student=request.user,
                mess=mess,
                plan_type=plan_type,
                start_date=today,
                end_date=end,
                price_paid=payment.amount,
                status='active',
                remaining_days=30,
                pause_remaining_days=30
            )
            payment.subscription = sub
            payment.save()

            WalletTransaction.objects.create(
                user=request.user,
                amount=payment.amount,
                transaction_type='subscription_payment',
                description=f"Monthly Subscription to {mess.mess_name} ({plan_type.upper()})"
            )

            Notification.objects.create(
                user=request.user,
                title="Subscription Active!",
                message=f"You are now subscribed to {mess.mess_name} ({plan_type.upper()}) until {end}.",
                notification_type='email'
            )
        elif purpose == 'cart_checkout':
            cart = Cart.objects.filter(student=request.user).first()
            if not cart or not cart.items.exists():
                raise ValueError('Cart is empty or missing for cart checkout.')
            if Decimal(cart.total_price) != payment.amount:
                raise ValueError('Cart total does not match payment amount.')

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

                if hasattr(item.meal, 'stock'):
                    item.meal.stock = max(0, item.meal.stock - item.quantity)
                    item.meal.save()

            cart.items.all().delete()

            payment.order = order
            payment.save()
            WalletTransaction.objects.create(
                user=request.user,
                amount=payment.amount,
                transaction_type='order_payment',
                description=f"Order Payment for Order #{order.id}"
            )
        elif purpose == 'wallet_recharge':
            profile, _ = StudentProfile.objects.get_or_create(user=request.user)
            profile.wallet_balance = (profile.wallet_balance or Decimal('0')) + payment.amount
            profile.save()
            WalletTransaction.objects.create(
                user=request.user,
                amount=payment.amount,
                transaction_type='credit',
                description='Wallet Recharge via Razorpay'
            )
        else:
            cart = Cart.objects.filter(student=request.user).first()
            if cart and cart.items.exists() and Decimal(cart.total_price) == payment.amount:
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

                    if hasattr(item.meal, 'stock'):
                        item.meal.stock = max(0, item.meal.stock - item.quantity)
                        item.meal.save()

                cart.items.all().delete()

                payment.order = order
                payment.save()
                WalletTransaction.objects.create(
                    user=request.user,
                    amount=payment.amount,
                    transaction_type='order_payment',
                    description=f"Order Payment for Order #{order.id}"
                )
            else:
                profile, _ = StudentProfile.objects.get_or_create(user=request.user)
                profile.wallet_balance = (profile.wallet_balance or Decimal('0')) + payment.amount
                profile.save()
                WalletTransaction.objects.create(
                    user=request.user,
                    amount=payment.amount,
                    transaction_type='credit',
                    description='Wallet Recharge via Razorpay'
                )

        mark_payment_success(
            payment,
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_signature=razorpay_signature,
            gateway_transaction_id=razorpay_payment_id
        )

    success_url = request.build_absolute_uri(reverse('payment_success', args=[payment.payment_id]))
    return JsonResponse({'status': 'success', 'redirect_url': success_url})


@require_POST
@student_required
def cancel_payment(request):
    payment_id = request.POST.get('payment_id')
    if not payment_id:
        return JsonResponse({'error': 'Missing payment identifier.'}, status=400)

    payment = Payment.objects.filter(payment_id=payment_id, user=request.user).first()
    if not payment:
        return JsonResponse({'error': 'Payment record not found.'}, status=404)

    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(id=payment.id)
        if payment.status != 'pending':
            return JsonResponse({'error': 'Payment cannot be cancelled because it is already processed.'}, status=400)
        mark_payment_cancelled(payment, reason='User cancelled payment')

    return JsonResponse({'status': 'cancelled', 'redirect_url': reverse('payment_failed', args=[payment.payment_id])})


@require_POST
@student_required
def fail_payment(request):
    payment_id = request.POST.get('payment_id')
    error_code = request.POST.get('error_code', 'UNKNOWN')
    error_reason = request.POST.get('error_reason', 'Unknown reason')
    error_description = request.POST.get('error_description', 'No description available')
    
    if not payment_id:
        return JsonResponse({'error': 'Missing payment identifier.'}, status=400)

    payment = Payment.objects.filter(payment_id=payment_id, user=request.user).first()
    if not payment:
        return JsonResponse({'error': 'Payment record not found.'}, status=404)
    
    # Log Razorpay error details
    logger.error(
        f'Razorpay payment failed: payment_id={payment_id}, '
        f'error_code={error_code}, error_reason={error_reason}, '
        f'error_description={error_description}'
    )
    
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(id=payment.id)
        if payment.status != 'pending':
            return JsonResponse({'error': 'Payment cannot be marked failed because it is already processed.'}, status=400)
        mark_payment_failed(payment, reason=f'{error_reason}: {error_description}')

    return JsonResponse({'status': 'failed', 'redirect_url': reverse('payment_failed', args=[payment.payment_id])})


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
        'gateway_order': {
            'id': payment.razorpay_order_id,
            'amount': int(payment.amount * 100) if payment.amount else None,
            'currency': 'INR'
        } if payment.razorpay_order_id else None,
        'razorpay_key_id': getattr(__import__('django.conf').conf.settings, 'RAZORPAY_KEY_ID', None),
    })


@require_POST
@student_required
def process_payment(request, payment_id):
    """Wallet simulation endpoint only. Razorpay payments must use verify_payment()."""
    payment = get_object_or_404(Payment, payment_id=payment_id, user=request.user)
    if payment.status != 'pending':
        messages.error(request, 'Payment has already been processed.')
        if payment.status == 'success':
            return redirect('payment_success', payment_id=payment.payment_id)
        return redirect('payment_failed', payment_id=payment.payment_id)

    # Only handle wallet simulation
    simulate_failure = request.POST.get('simulate_failure') == 'true'
    if simulate_failure:
        payment.status = 'failed'
        payment.save()
        return redirect('payment_failed', payment_id=payment.payment_id)

    # Wallet payments are handled in checkout_cart() and subscribe_plan() directly
    # This endpoint should not be used for Razorpay completion
    messages.error(request, 'Invalid payment processing request.')
    return redirect('payment_failed', payment_id=payment.payment_id)


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
    promo_code = request.POST.get('promo_code', '').strip().upper()
    try:
        amount_dec = Decimal(amount)
        if amount_dec <= Decimal('0'):
            raise InvalidOperation
    except (InvalidOperation, TypeError, ValueError):
        messages.error(request, 'Invalid amount')
        return redirect('wallet_detail')

    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    txs = WalletTransaction.objects.filter(user=request.user).order_by('-created_at')

    with transaction.atomic():
        payment = create_payment_record(
            user=request.user,
            amount=amount_dec,
            payment_method='online',
            gateway='razorpay'
        )
        razorpay_order_id = create_razorpay_order(
            amount=amount_dec,
            receipt=str(payment.payment_id),
            notes={
                'purpose': 'wallet_recharge',
                'user_id': str(request.user.id),
                'promo_code': promo_code or 'NONE'
            }
        )
        payment.razorpay_order_id = razorpay_order_id
        payment.save()

    return render(request, 'student/wallet.html', {
        'profile': profile,
        'transactions': txs,
        'razorpay_order_id': razorpay_order_id,
        'razorpay_key_id': settings.RAZORPAY_KEY_ID,
        'amount': amount_dec,
        'payment_id': str(payment.payment_id),
        'promo_code': promo_code,
    })


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
        refund_payment(payment)
        messages.success(request, 'Refund processed')
    return redirect('vendor_earnings')
