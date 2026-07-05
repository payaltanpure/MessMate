import datetime
import random
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from core.decorators import student_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db import transaction

from vendor.models import Mess, Meal
from accounts.models import User, StudentProfile
from .models import (
    Subscription, Order, OrderItem, Cart, CartItem,
    WalletTransaction, Payment, Review, Complaint, Notification
)
from core.ai_services import (
    recommend_messes, recommend_meals, 
    analyze_review_sentiment, classify_complaint_nlp
)

# PDF Generation Support
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


@student_required
def student_dashboard(request):
    """
    Displays the student dashboard showing subscription status, wallet balance, active orders, and notifications.
    """
    if request.user.role != 'student':
        messages.error(request, "Access Denied. Students only.")
        return redirect('login')
        
    profile, created = StudentProfile.objects.get_or_create(user=request.user)
    
    # Active Subscription
    subscription = Subscription.objects.filter(student=request.user, status='active').first()
    if not subscription:
        subscription = Subscription.objects.filter(student=request.user, status='paused').first()

    # Active Orders
    orders = Order.objects.filter(student=request.user).order_by('-order_date')[:5]
    
    # Wallet Transactions
    txs = WalletTransaction.objects.filter(user=request.user).order_by('-created_at')[:5]
    
    # Active Complaints
    complaints = Complaint.objects.filter(student=request.user).order_by('-created_at')[:5]

    # AI Smart Meal Recommendations
    smart_meals = recommend_meals(request.user)

    context = {
        'profile': profile,
        'subscription': subscription,
        'orders': orders,
        'transactions': txs,
        'complaints': complaints,
        'smart_meals': smart_meals,
    }
    return render(request, 'student/dashboard.html', context)


@student_required
def edit_profile(request):
    """
    Allows the student to edit their profile information and upload a photo.
    """
    if request.user.role != 'student':
        return redirect('login')
        
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        request.user.first_name = request.POST.get('first_name', '')
        request.user.last_name = request.POST.get('last_name', '')
        request.user.phone = request.POST.get('phone', '')
        request.user.address = request.POST.get('address', '')
        request.user.save()

        if 'photo' in request.FILES:
            profile.photo = request.FILES['photo']
        profile.save()
        
        messages.success(request, "Profile updated successfully!")
        return redirect('student_dashboard')

    return render(request, 'student/edit_profile.html', {'profile': profile})


@student_required
def wallet_detail(request):
    """
    Wallet system: add money, check balance and transaction logs.
    """
    if request.user.role != 'student':
        return redirect('login')
        
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    txs = WalletTransaction.objects.filter(user=request.user).order_by('-created_at')
    
    if request.method == "POST":
        amount_str = request.POST.get('amount')
        promo_code = request.POST.get('promo_code', '').strip().upper()
        try:
            amount = Decimal(str(amount_str))
            if amount <= Decimal('0'):
                raise InvalidOperation

            # Simulate Razorpay deposit flow
            with transaction.atomic():
                # Use Decimal arithmetic for money fields
                profile.wallet_balance = (profile.wallet_balance or Decimal('0')) + amount

                # Apply cashback heuristic (e.g. SMART10 promo code)
                cashback = Decimal('0')
                if promo_code == "SMART10":
                    cashback = (amount * Decimal('0.1')).quantize(Decimal('0.01'))
                    profile.cashback_balance = (profile.cashback_balance or Decimal('0')) + cashback

                profile.save()

                # Create transactions
                WalletTransaction.objects.create(
                    user=request.user,
                    amount=amount,
                    transaction_type='credit',
                    description=f"Added funds via Online Payment. Promo Code: {promo_code or 'None'}"
                )
                if cashback > 0:
                    WalletTransaction.objects.create(
                        user=request.user,
                        amount=cashback,
                        transaction_type='cashback',
                        description="10% Cashback applied on funding wallet"
                    )

            messages.success(request, f"Successfully deposited Rs.{amount} to your wallet! {f'Rs.{cashback} cashback credited.' if cashback > 0 else ''}")
            return redirect('wallet_detail')
        except (InvalidOperation, TypeError):
            messages.error(request, "Please enter a valid deposit amount.")
            
    return render(request, 'student/wallet.html', {'profile': profile, 'transactions': txs})


@student_required
def mess_detail(request, mess_id):
    """
    Details page of a mess showcasing subscription pricing, menu, ratings, reviews.
    """
    mess = get_object_or_404(Mess, id=mess_id)
    meals = mess.meals.filter(is_available=True)
    reviews = mess.reviews.all().order_by('-created_at')
    
    # Check if user already subscribed
    current_sub = Subscription.objects.filter(student=request.user, mess=mess, status__in=['active', 'paused']).first()
    
    return render(request, 'student/mess_detail.html', {
        'mess': mess,
        'meals': meals,
        'reviews': reviews,
        'current_sub': current_sub
    })


@student_required
def subscribe_plan(request, mess_id):
    """
    Creates a new monthly subscription using wallet balance or Razorpay checkout simulation.
    """
    if request.user.role != 'student':
        return redirect('login')
        
    mess = get_object_or_404(Mess, id=mess_id)
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    
    if request.method == "POST":
        plan_type = request.POST.get('plan_type') # lunch, dinner, both
        
        # Calculate price based on choice
        if plan_type == 'lunch':
            price = mess.monthly_price_lunch
        elif plan_type == 'dinner':
            price = mess.monthly_price_dinner
        else:
            price = mess.monthly_price_both
            
        if price <= 0:
            messages.error(request, "Invalid plan or pricing.")
            return redirect('mess_detail', mess_id=mess.id)
            
        # Wallet logic
        total_bal = profile.wallet_balance + profile.cashback_balance
        if total_bal < price:
            # Not enough money, prompt deposit
            messages.error(request, f"Insufficient wallet balance. Plan costs Rs.{price}, you have Rs.{total_bal}.")
            return redirect('wallet_detail')
            
        with transaction.atomic():
            # Deduct from cashback first, then main wallet
            remaining_price = price
            if profile.cashback_balance >= price:
                profile.cashback_balance -= price
                remaining_price = 0
            else:
                remaining_price -= profile.cashback_balance
                profile.cashback_balance = 0
                profile.wallet_balance -= remaining_price
            profile.save()
            
            # Cancel any existing active subscriptions for the same mess first
            Subscription.objects.filter(student=request.user, mess=mess, status='active').update(status='expired')
            
            # Create subscription
            today = datetime.date.today()
            end = today + datetime.timedelta(days=30)
            sub = Subscription.objects.create(
                student=request.user,
                mess=mess,
                plan_type=plan_type,
                start_date=today,
                end_date=end,
                price_paid=price,
                status='active',
                remaining_days=30
            )
            
            # Transaction log
            WalletTransaction.objects.create(
                user=request.user,
                amount=price,
                transaction_type='debit',
                description=f"Monthly Subscription to {mess.mess_name} ({plan_type.upper()})"
            )
            
            # Log Razorpay Payment Simulation
            Payment.objects.create(
                subscription=sub,
                user=request.user,
                razorpay_order_id="sub_rp_mock_" + str(sub.id),
                razorpay_payment_id="pay_rp_mock_" + str(sub.id),
                razorpay_signature="sig_mock",
                amount=price,
                status='success'
            )
            
            # Notification log
            Notification.objects.create(
                user=request.user,
                title="Subscription Active!",
                message=f"You are now subscribed to {mess.mess_name} ({plan_type.upper()}) until {end}.",
                notification_type='email'
            )

        messages.success(request, f"Subscribed successfully to {mess.mess_name}!")
        return redirect('student_dashboard')
        
    return redirect('mess_detail', mess_id=mess.id)


@require_POST
@student_required
def pause_subscription(request, sub_id):
    sub = get_object_or_404(Subscription, id=sub_id, student=request.user)
    if sub.status == 'active':
        today = datetime.date.today()
        sub.status = 'paused'
        sub.pause_date = today
        # Calculate how many days are left on the subscription
        days_passed = (today - sub.start_date).days
        sub.pause_remaining_days = max(1, 30 - days_passed)
        sub.save()
        messages.success(request, f"Subscription paused! You have {sub.pause_remaining_days} remaining days frozen.")
    else:
        messages.error(request, "Subscription is not active and cannot be paused.")
    return redirect('student_dashboard')


@require_POST
@student_required
def resume_subscription(request, sub_id):
    sub = get_object_or_404(Subscription, id=sub_id, student=request.user)
    if sub.status == 'paused':
        today = datetime.date.today()
        sub.status = 'active'
        # Push the end date forward based on remaining paused days
        sub.start_date = today
        sub.end_date = today + datetime.timedelta(days=sub.pause_remaining_days)
        sub.pause_date = None
        sub.save()
        messages.success(request, f"Welcome back! Subscription resumed. Expiring on {sub.end_date}.")
    else:
        messages.error(request, "Subscription is not paused.")
    return redirect('student_dashboard')


@require_POST
@student_required
def cancel_subscription(request, sub_id):
    sub = get_object_or_404(Subscription, id=sub_id, student=request.user)
    if sub.status in ['active', 'paused']:
        with transaction.atomic():
            sub.status = 'cancelled'
            sub.save()
            
            # Heuristic Refund: 80% value of remaining days returned to wallet
            rate_per_day = sub.price_paid / 30
            refund_days = sub.pause_remaining_days if sub.pause_date else max(1, (sub.end_date - datetime.date.today()).days)
            refund_amount = round(rate_per_day * refund_days * 0.8, 2)
            
            profile, _ = StudentProfile.objects.get_or_create(user=request.user)
            profile.wallet_balance = (profile.wallet_balance or Decimal('0')) + Decimal(str(refund_amount))
            profile.save()
            
            WalletTransaction.objects.create(
                user=request.user,
                amount=refund_amount,
                transaction_type='refund',
                description=f"Refund for cancelling subscription to {sub.mess.mess_name}"
            )
            
            messages.success(request, f"Subscription cancelled. Rs.{refund_amount} refunded to wallet.")
    else:
        messages.error(request, "No active subscription to cancel.")
    return redirect('student_dashboard')


# TIFFIN ORDERING & CART SYSTEM
@student_required
def view_cart(request):
    cart, _ = Cart.objects.get_or_create(student=request.user)
    items = cart.items.all()
    return render(request, 'student/cart.html', {'cart': cart, 'items': items})


@require_POST
@student_required
def add_to_cart(request, meal_id):
    meal = get_object_or_404(Meal, id=meal_id)
    cart, _ = Cart.objects.get_or_create(student=request.user)
    
    # Cart can only contain items from one mess at a time to simplify delivery
    first_item = cart.items.first()
    if first_item and first_item.meal.mess != meal.mess:
        cart.items.all().delete()
        messages.info(request, "Cart cleared: You can only order from one mess at a time.")

    cart_item, created = CartItem.objects.get_or_create(cart=cart, meal=meal)
    if not created:
        cart_item.quantity += 1
        cart_item.save()
        
    messages.success(request, f"Added {meal.name} to cart.")
    return redirect('view_cart')


@require_POST
@student_required
def update_cart(request, item_id):
    item = get_object_or_404(CartItem, id=item_id, cart__student=request.user)
    action = request.POST.get('action')
    if action == 'increase':
        item.quantity += 1
        item.save()
    elif action == 'decrease':
        item.quantity -= 1
        if item.quantity <= 0:
            item.delete()
        else:
            item.save()
    elif action == 'remove':
        item.delete()
        
    return redirect('view_cart')


@student_required
def checkout_cart(request):
    cart = get_object_or_404(Cart, student=request.user)
    if not cart.items.exists():
        messages.error(request, "Your cart is empty.")
        return redirect('view_cart')
        
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    # Ensure Decimal arithmetic for totals
    try:
        total_cost = Decimal(cart.total_price)
    except Exception:
        total_cost = Decimal(str(cart.total_price))
    
    if request.method == "POST":
        payment_method = request.POST.get('payment_method') # wallet or online
        
        if payment_method == 'wallet':
            total_bal = profile.wallet_balance + profile.cashback_balance
            if total_bal < total_cost:
                messages.error(request, "Insufficient wallet balance.")
                return redirect('view_cart')
                
            with transaction.atomic():
                # Deduct
                remaining = total_cost
                if profile.cashback_balance >= remaining:
                    profile.cashback_balance -= remaining
                    remaining = 0
                else:
                    remaining -= profile.cashback_balance
                    profile.cashback_balance = 0
                    profile.wallet_balance -= remaining
                profile.save()
                
                # Create Order
                mess = cart.items.first().meal.mess
                otp = f"{random.randint(100000, 999999)}"
                order = Order.objects.create(
                    student=request.user,
                    mess=mess,
                    total_amount=total_cost,
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
                    
                # Clear Cart
                cart.items.all().delete()
                
                # Transaction
                WalletTransaction.objects.create(
                    user=request.user,
                    amount=total_cost,
                    transaction_type='debit',
                    description=f"Tiffin Order #{order.id} from {mess.mess_name}"
                )
                
                # Success Payment
                Payment.objects.create(
                    order=order,
                    user=request.user,
                    razorpay_order_id=f"order_rp_mock_{order.id}",
                    razorpay_payment_id=f"pay_rp_mock_{order.id}",
                    amount=total_cost,
                    status='success'
                )

            messages.success(request, f"Order #{order.id} placed successfully using Wallet!")
            return redirect('student_dashboard')
            
        else:
            # Online checkout: create pending payment and redirect to payment page
            payment = Payment.objects.create(
                user=request.user,
                amount=total_cost,
                payment_method='online',
                payment_gateway='razorpay',
                status='pending'
            )
            return redirect('payment_page', payment_id=payment.payment_id)

    return render(request, 'student/checkout.html', {'cart': cart})


@student_required
def track_order(request, order_id):
    order = get_object_or_404(Order, id=order_id, student=request.user)
    return render(request, 'student/track_order.html', {'order': order})


# REVIEWS AND RATINGS
@require_POST
@student_required
def add_review(request, mess_id):
    mess = get_object_or_404(Mess, id=mess_id)
    if request.method == "POST":
        rating = request.POST.get('rating')
        comment = request.POST.get('comment')
        photo = request.FILES.get('photo', None)
        
        sentiment = analyze_review_sentiment(comment)
        
        Review.objects.create(
            student=request.user,
            mess=mess,
            rating=int(rating),
            comment=comment,
            photo=photo,
            sentiment=sentiment
        )
        messages.success(request, "Thank you for your feedback! Your review was analyzed as: " + sentiment.upper())
        return redirect('mess_detail', mess_id=mess.id)
        
    return redirect('mess_detail', mess_id=mess.id)


# COMPLAINT MANAGEMENT
@student_required
def submit_complaint(request):
    if request.method == "POST":
        description = request.POST.get('description')
        mess_id = request.POST.get('mess_id')
        order_id = request.POST.get('order_id')
        category = request.POST.get('category')
        
        mess = Mess.objects.filter(id=mess_id).first() if mess_id else None
        order = Order.objects.filter(id=order_id).first() if order_id else None
        
        if not category:
            category = classify_complaint_nlp(description)
        
        Complaint.objects.create(
            student=request.user,
            mess=mess,
            order=order,
            category=category,
            description=description,
            status='open'
        )
        messages.success(request, f"Complaint raised successfully under category: {category.replace('_', ' ').title()}")
        return redirect('student_dashboard')
        
    messes = Mess.objects.filter(is_active=True)
    orders = Order.objects.filter(student=request.user).order_by('-order_date')[:10]
    return render(request, 'student/complaint.html', {'messes': messes, 'orders': orders})


# GENERATE PDF INVOICES
@student_required
def download_invoice(request, payment_id):
    payment = Payment.objects.filter(id=payment_id, user=request.user).first()
    transaction = None
    if not payment:
        transaction = WalletTransaction.objects.filter(id=payment_id, user=request.user).first()
        if not transaction:
            return get_object_or_404(Payment, id=payment_id, user=request.user)

    invoice_id = payment.id if payment else transaction.id
    invoice_user = payment.user if payment else transaction.user
    invoice_date = payment.created_at if payment else transaction.created_at
    invoice_amount = payment.amount if payment else transaction.amount
    invoice_desc = ''
    if payment:
        if payment.subscription:
            invoice_desc = f"Monthly Subscription to {payment.subscription.mess.mess_name}"
        elif payment.order:
            invoice_desc = f"Tiffin Order #{payment.order.id} from {payment.order.mess.mess_name}"
        else:
            invoice_desc = "Wallet Funding Deposit"
    else:
        invoice_desc = transaction.description

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="invoice_{invoice_id}.pdf"'
    
    if HAS_REPORTLAB:
        # Create standard PDF layout
        p = canvas.Canvas(response, pagesize=letter)
        p.setFont("Helvetica-Bold", 20)
        p.drawString(100, 750, "SMARTMESS AI - INVOICE")
        p.setFont("Helvetica", 12)
        p.drawString(100, 720, f"Invoice ID: {invoice_id}")
        p.drawString(100, 700, f"Date: {invoice_date.strftime('%Y-%m-%d %H:%M')}")
        p.drawString(100, 680, f"Customer: {invoice_user.username}")
        p.drawString(100, 660, f"Email: {invoice_user.email}")
        
        p.line(100, 640, 500, 640)
        
        p.drawString(100, 610, "Description")
        p.drawString(400, 610, "Amount")
        
        p.drawString(100, 580, invoice_desc)
        p.drawString(400, 580, f"Rs. {invoice_amount}")
        
        p.line(100, 550, 500, 550)
        
        p.drawString(300, 520, "Total Paid:")
        p.drawString(400, 520, f"Rs. {invoice_amount}")
        
        p.setFont("Helvetica-Bold", 10)
        p.drawString(100, 450, "Thank you for using SMARTMESS AI!")
        p.drawString(100, 435, "This is a computer generated invoice and requires no physical signature.")
        p.showPage()
        p.save()
        return response
    else:
        # Fallback to high-quality formatted HTML/Text invoice if ReportLab is missing
        invoice_html = f"""
        <html>
        <head>
            <title>Invoice {invoice_id}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 50px; color: #333; }}
                .header {{ border-bottom: 2px solid #ccc; padding-bottom: 20px; margin-bottom: 30px; }}
                .header h1 {{ margin: 0; color: #ff5e62; }}
                .details {{ margin-bottom: 20px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th, td {{ padding: 12px; border: 1px solid #ddd; text-align: left; }}
                th {{ background-color: #f8f9fa; }}
                .total {{ text-align: right; font-weight: bold; font-size: 1.2em; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>SMARTMESS AI</h1>
                <p>Hostel Mess & Tiffin Management Invoice</p>
            </div>
            <div class="details">
                <p><strong>Invoice ID:</strong> {invoice_id}</p>
                <p><strong>Date:</strong> {invoice_date.strftime('%Y-%m-%d %H:%M')}</p>
                <p><strong>Customer:</strong> {invoice_user.username} ({invoice_user.email})</p>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Description</th>
                        <th>Amount</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>
                            {invoice_desc}
                        </td>
                        <td>Rs. {invoice_amount}</td>
                    </tr>
                </tbody>
            </table>
            <div class="total">
                Total Paid: Rs. {invoice_amount}
            </div>
            <p style="margin-top:50px; font-size:0.9em; color:#777; text-align:center;">
                Thank you for using SMARTMESS AI! (ReportLab not installed; printable fallback output displayed)
            </p>
            <script>window.print();</script>
        </body>
        </html>
        """
        return HttpResponse(invoice_html)