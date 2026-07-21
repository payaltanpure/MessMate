import csv
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import wraps

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import User, StudentProfile, VendorProfile, DeliveryBoyProfile
from core.ai_services import get_ai_insights, get_recommended_meals, predict_meal_demands
from core.delivery_views import get_delivery_boy_metrics, transition_order_status
from core.email_services import send_vendor_notification
from core.maps_service import build_directions_url, build_open_maps_url, get_maps_config, get_mess_map_data
from core.email_services import (
    send_admin_notification,
    send_complaint_resolution_email,
    send_critical_alert_email,
    send_daily_report_email,
    send_vendor_notification,
)
from core.sms_service import send_sms
from core.weather_service import get_weather, get_weather_impact
from notifications.firebase_service import send_push_notification
from student.models import Complaint, Order, OrderItem, Payment, Review, Subscription, WalletTransaction
from vendor.models import Mess, Meal
from .forms import MealAdminForm, MessAdminForm


def login_required(view_func=None, **kwargs):
    def decorator(func):
        @wraps(func)
        def _wrapped_view(request, *args, **kwargs):
            if request.user.is_authenticated:
                return func(request, *args, **kwargs)

            messages.info(request, 'Please sign in with an administrator account.')
            return redirect('adminpanel:admin_login')

        return _wrapped_view

    if view_func is None:
        return decorator
    return decorator(view_func)


def admin_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_authenticated and (request.user.role == 'admin' or request.user.is_superuser):
            return view_func(request, *args, **kwargs)

        if request.user.is_authenticated:
            messages.error(request, 'Access Denied. Admins only.')
            return redirect('home')

        messages.info(request, 'Please sign in with an administrator account.')
        return redirect('adminpanel:admin_login')

    return _wrapped_view


def admin_login(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        if not username or not password:
            messages.error(request, 'Please enter both username and password.')
            return render(request, 'adminpanel/login.html', {
                'username': username,
                'errors': {'username': not username, 'password': not password},
            })

        user = authenticate(request, username=username, password=password)

        if user is not None and (user.role == 'admin' or user.is_superuser):
            login(request, user)
            messages.success(request, f'Welcome back, {user.username}!')
            return redirect('adminpanel:admin_dashboard')

        if user is not None:
            logout(request)
            messages.error(request, 'Only administrator accounts can access the admin dashboard.')
            return redirect('adminpanel:admin_login')

        messages.error(request, 'Invalid username or password.')

        return render(request, 'adminpanel/login.html', {
            'username': username,
            'errors': {'username': False, 'password': False},
        })

    return render(request, 'adminpanel/login.html', {
        'username': '',
        'errors': {'username': False, 'password': False},
    })


def admin_logout(request):
    logout(request)
    messages.success(request, 'You have been logged out from the admin area.')
    return redirect('adminpanel:admin_login')


@login_required(login_url='login')
@admin_required
def admin_dashboard(request):
    students = User.objects.filter(role='student').order_by('-date_joined')[:5]
    vendors = User.objects.filter(role='vendor').order_by('-date_joined')[:5]
    complaints = Complaint.objects.select_related('student', 'mess').order_by('-created_at')[:5]
    orders = Order.objects.select_related('student', 'mess').order_by('-order_date')[:5]

    total_students = User.objects.filter(role='student').count()
    total_vendors = User.objects.filter(role='vendor').count()
    total_messes = Mess.objects.count()
    total_orders = Order.objects.count()
    active_subscriptions = Subscription.objects.filter(status='active').count()
    total_complaints = Complaint.objects.count()

    successful_payments = Payment.objects.filter(status='success').aggregate(total=Sum('amount'))['total'] or Decimal('0')
    revenue = successful_payments if successful_payments else Decimal('0')

    today_orders = Order.objects.filter(order_date__date=timezone.now().date()).count()

    all_delivery_boys = User.objects.filter(role='delivery').select_related('delivery_profile').order_by('-date_joined')
    total_delivery_boys = all_delivery_boys.count()
    available_delivery_boys = all_delivery_boys.filter(delivery_profile__availability_status='available').count()
    busy_delivery_boys = all_delivery_boys.filter(delivery_profile__availability_status='busy').count()

    delivery_boy_stats = []
    for db in all_delivery_boys[:10]:
        metrics = get_delivery_boy_metrics(db)
        delivery_boy_stats.append({
            'delivery_boy': db,
            'profile': metrics['profile'],
            'assigned_orders': metrics['assigned_orders'],
            'active_deliveries': metrics['active_deliveries'],
            'completed_deliveries': metrics['completed_deliveries'],
            'pending_deliveries': metrics['pending_deliveries'],
            'total_deliveries': metrics['total_deliveries'],
        })

    recent_deliveries = Order.objects.filter(status__in=['delivered', 'completed'], delivery_boy__isnull=False).select_related('student', 'mess', 'delivery_boy').order_by('-order_date')[:8]
    pending_orders = Order.objects.filter(status__in=['pending', 'accepted', 'preparing', 'ready_for_pickup']).select_related('student', 'mess').order_by('order_date')[:8]
    out_for_delivery_orders = Order.objects.filter(status='out_for_delivery').select_related('student', 'mess', 'delivery_boy').order_by('-order_date')[:8]
    top_delivery_boys = sorted(delivery_boy_stats, key=lambda item: item['completed_deliveries'], reverse=True)[:5]
    vendor_order_stats = User.objects.filter(role='vendor').annotate(order_count=Count('messes__orders')).order_by('-order_count')[:8]

    total_assigned_orders = Order.objects.filter(delivery_boy__isnull=False).exclude(status__in=['delivered', 'completed', 'cancelled']).count()
    total_active_deliveries = Order.objects.filter(status__in=['picked_up', 'out_for_delivery']).count()
    total_completed_deliveries = Order.objects.filter(status__in=['delivered', 'completed'], delivery_boy__isnull=False).count()
    total_pending_deliveries = Order.objects.filter(status__in=['pending', 'accepted', 'preparing', 'ready_for_pickup']).count()

    all_meals = Meal.objects.select_related('mess').order_by('mess__mess_name', 'name')
    student_users = User.objects.filter(role='student')

    recommendation_scores = {meal.id: 0 for meal in all_meals}
    mess_recommendation_scores = {}

    for student in student_users:
        try:
            for meal in get_recommended_meals(student):
                if meal.id in recommendation_scores:
                    recommendation_scores[meal.id] += 1
                    mess_recommendation_scores[meal.mess_id] = mess_recommendation_scores.get(meal.mess_id, 0) + 1
        except Exception:
            continue

    top_recommended = [
        {'meal': meal, 'score': recommendation_scores.get(meal.id, 0)}
        for meal in all_meals
    ]
    top_recommended.sort(key=lambda item: item['score'], reverse=True)
    top_recommended = top_recommended[:5]

    mess_distribution = [
        {'mess': mess, 'score': mess_recommendation_scores.get(mess.id, 0)}
        for mess in Mess.objects.all().order_by('mess_name')
    ]
    mess_distribution.sort(key=lambda item: item['score'], reverse=True)

    recommendation_stats = {
        'students_evaluated': student_users.count(),
        'total_meals': all_meals.count(),
        'top_score': top_recommended[0]['score'] if top_recommended else 0,
        'avg_score': round(sum(item['score'] for item in top_recommended) / len(top_recommended), 2) if top_recommended else 0,
    }

    weather = get_weather('Bengaluru')
    weather_impact = get_weather_impact('Bengaluru')

    context = {
        'total_students': total_students,
        'total_vendors': total_vendors,
        'total_messes': total_messes,
        'total_orders': total_orders,
        'active_subscriptions': active_subscriptions,
        'total_complaints': total_complaints,
        'revenue': revenue,
        'today_orders': today_orders,
        'latest_orders': orders,
        'latest_students': students,
        'latest_vendors': vendors,
        'latest_complaints': complaints,
        'recommendation_stats': recommendation_stats,
        'top_recommended': top_recommended,
        'mess_distribution': mess_distribution,
        'weather': weather,
        'weather_impact': weather_impact,
        # Delivery Boy Statistics
        'total_delivery_boys': total_delivery_boys,
        'available_delivery_boys': available_delivery_boys,
        'busy_delivery_boys': busy_delivery_boys,
        'delivery_boy_stats': delivery_boy_stats,
        'vendor_order_stats': vendor_order_stats,
        'recent_deliveries': recent_deliveries,
        'pending_orders': pending_orders,
        'out_for_delivery_orders': out_for_delivery_orders,
        'top_delivery_boys': top_delivery_boys,
        'total_assigned_orders': total_assigned_orders,
        'total_active_deliveries': total_active_deliveries,
        'total_completed_deliveries': total_completed_deliveries,
        'total_pending_deliveries': total_pending_deliveries,
    }
    return render(request, 'adminpanel/dashboard.html', context)


@login_required(login_url='login')
@admin_required
def manage_students(request):
    queryset = User.objects.filter(role='student').select_related('student_profile').order_by('-date_joined')
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')

    if query:
        queryset = queryset.filter(Q(username__icontains=query) | Q(email__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query))
    if status == 'active':
        queryset = queryset.filter(is_active=True)
    elif status == 'blocked':
        queryset = queryset.filter(is_active=False)

    paginator = Paginator(queryset, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'adminpanel/manage_students.html', {
        'page_obj': page_obj,
        'query': query,
        'status': status,
    })


@login_required(login_url='login')
@admin_required
def toggle_student_status(request, user_id):
    if request.method == 'POST':
        student = get_object_or_404(User, id=user_id, role='student')
        student.is_active = not student.is_active
        student.save()
        action = 'unblocked' if student.is_active else 'blocked'
        messages.success(request, f'Student {student.username} {action} successfully.')
    return redirect('adminpanel:manage_students')


@login_required(login_url='login')
@admin_required
def student_profile(request, user_id):
    student = get_object_or_404(User, id=user_id, role='student')
    profile = getattr(student, 'student_profile', None)
    return render(request, 'adminpanel/student_profile.html', {
        'student': student,
        'profile': profile,
    })


@login_required(login_url='login')
@admin_required
def manage_messes(request):
    queryset = Mess.objects.select_related('vendor').order_by('-id')
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')

    if query:
        queryset = queryset.filter(
            Q(mess_name__icontains=query) |
            Q(vendor__username__icontains=query) |
            Q(vendor__first_name__icontains=query) |
            Q(vendor__last_name__icontains=query) |
            Q(location_name__icontains=query)
        )
    if status == 'active':
        queryset = queryset.filter(is_active=True)
    elif status == 'inactive':
        queryset = queryset.filter(is_active=False)

    paginator = Paginator(queryset, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'adminpanel/manage_messes.html', {
        'page_obj': page_obj,
        'query': query,
        'status': status,
        'maps_config': get_maps_config(),
    })


@login_required(login_url='login')
@admin_required
def mess_detail(request, mess_id):
    mess = get_object_or_404(Mess, id=mess_id)
    meals = mess.meals.all().order_by('meal_type', 'name')
    active_subscriptions = Subscription.objects.filter(mess=mess, status='active').count()
    maps_config = get_maps_config()
    mess_map_data = get_mess_map_data(mess)
    directions_url = build_directions_url(mess)
    open_maps_url = build_open_maps_url(mess)

    return render(request, 'adminpanel/mess_detail.html', {
        'mess': mess,
        'meals': meals,
        'active_subscriptions': active_subscriptions,
        'google_maps_api_key': maps_config['api_key'],
        'maps_config': maps_config,
        'mess_map_data': mess_map_data,
        'directions_url': directions_url,
        'open_maps_url': open_maps_url,
    })


@login_required(login_url='login')
@admin_required
def edit_mess(request, mess_id):
    mess = get_object_or_404(Mess, id=mess_id)
    if request.method == 'POST':
        form = MessAdminForm(request.POST, request.FILES, instance=mess)
        if form.is_valid():
            form.save()
            messages.success(request, 'Mess updated successfully.')
            return redirect('adminpanel:mess_detail', mess_id=mess.id)
    else:
        form = MessAdminForm(instance=mess)

    return render(request, 'adminpanel/edit_mess.html', {'form': form, 'mess': mess})


@login_required(login_url='login')
@admin_required
def toggle_mess_status(request, mess_id):
    if request.method == 'POST':
        mess = get_object_or_404(Mess, id=mess_id)
        mess.is_active = not mess.is_active
        mess.save()
        action = 'activated' if mess.is_active else 'deactivated'
        messages.success(request, f'Mess {mess.mess_name} {action} successfully.')
    return redirect('adminpanel:manage_messes')


@login_required(login_url='login')
@admin_required
def approve_mess(request, mess_id):
    if request.method == 'POST':
        mess = get_object_or_404(Mess, id=mess_id)
        mess.is_active = True
        mess.save()
        messages.success(request, f'Mess {mess.mess_name} approved successfully.')
    return redirect('adminpanel:manage_messes')


@login_required(login_url='login')
@admin_required
def reject_mess(request, mess_id):
    if request.method == 'POST':
        mess = get_object_or_404(Mess, id=mess_id)
        mess.is_active = False
        mess.save()
        messages.success(request, f'Mess {mess.mess_name} rejected successfully.')
    return redirect('adminpanel:manage_messes')


@login_required(login_url='login')
@admin_required
def delete_mess(request, mess_id):
    if request.method == 'POST':
        mess = get_object_or_404(Mess, id=mess_id)
        mess.delete()
        messages.success(request, 'Mess deleted successfully.')
    return redirect('adminpanel:manage_messes')


@login_required(login_url='login')
@admin_required
def manage_meals(request):
    queryset = Meal.objects.select_related('mess', 'mess__vendor').order_by('-id')
    query = request.GET.get('q', '').strip()
    meal_type = request.GET.get('meal_type', '')
    vendor_id = request.GET.get('vendor', '')
    mess_id = request.GET.get('mess', '')
    availability = request.GET.get('availability', '')

    if query:
        queryset = queryset.filter(Q(name__icontains=query) | Q(menu_items__icontains=query))
    if meal_type:
        queryset = queryset.filter(meal_type=meal_type)
    if vendor_id:
        queryset = queryset.filter(mess__vendor_id=vendor_id)
    if mess_id:
        queryset = queryset.filter(mess_id=mess_id)
    if availability == 'available':
        queryset = queryset.filter(is_available=True)
    elif availability == 'unavailable':
        queryset = queryset.filter(is_available=False)

    paginator = Paginator(queryset, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'query': query,
        'meal_type': meal_type,
        'vendor_id': vendor_id,
        'mess_id': mess_id,
        'availability': availability,
        'vendors': User.objects.filter(role='vendor').order_by('username'),
        'messes': Mess.objects.order_by('mess_name'),
    }
    return render(request, 'adminpanel/manage_meals.html', context)


@login_required(login_url='login')
@admin_required
def meal_detail(request, meal_id):
    meal = get_object_or_404(Meal, id=meal_id)
    return render(request, 'adminpanel/meal_detail.html', {'meal': meal})


@login_required(login_url='login')
@admin_required
def edit_meal(request, meal_id):
    meal = get_object_or_404(Meal, id=meal_id)
    if request.method == 'POST':
        form = MealAdminForm(request.POST, request.FILES, instance=meal)
        if form.is_valid():
            form.save()
            messages.success(request, 'Meal updated successfully.')
            return redirect('adminpanel:meal_detail', meal_id=meal.id)
    else:
        form = MealAdminForm(instance=meal)

    return render(request, 'adminpanel/edit_meal.html', {'form': form, 'meal': meal})


@login_required(login_url='login')
@admin_required
def toggle_meal_status(request, meal_id):
    if request.method == 'POST':
        meal = get_object_or_404(Meal, id=meal_id)
        meal.is_available = not meal.is_available
        meal.save()
        action = 'enabled' if meal.is_available else 'disabled'
        messages.success(request, f'Meal {meal.name} {action} successfully.')
    return redirect('adminpanel:manage_meals')


@login_required(login_url='login')
@admin_required
def delete_meal(request, meal_id):
    if request.method == 'POST':
        meal = get_object_or_404(Meal, id=meal_id)
        meal.delete()
        messages.success(request, 'Meal deleted successfully.')
    return redirect('adminpanel:manage_meals')


@login_required(login_url='login')
@admin_required
def manage_orders(request):
    queryset = Order.objects.select_related('student', 'mess', 'mess__vendor').order_by('-order_date')
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    payment_status = request.GET.get('payment_status', '')

    if query:
        queryset = queryset.filter(
            Q(id__icontains=query) |
            Q(student__username__icontains=query) |
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(mess__vendor__username__icontains=query) |
            Q(mess__vendor__first_name__icontains=query) |
            Q(mess__vendor__last_name__icontains=query)
        )
    if status:
        queryset = queryset.filter(status=status)
    if payment_status:
        order_ids = Payment.objects.filter(status=payment_status).values_list('order_id', flat=True)
        queryset = queryset.filter(id__in=order_ids)

    paginator = Paginator(queryset, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    for order in page_obj:
        payment = order.payments.order_by('-created_at').first() if hasattr(order, 'payments') else None
        order.payment_status = payment.status if payment else 'n/a'
        order.payment_status_display = payment.get_status_display() if payment else 'N/A'
        order.payment_method = payment.payment_method if payment else 'N/A'
        order.payment_amount = payment.amount if payment else order.total_amount
        order.delivery_time = order.order_date if order.status in {'delivered', 'out_for_delivery'} else None

    context = {
        'page_obj': page_obj,
        'query': query,
        'status': status,
        'payment_status': payment_status,
        'order_status_choices': Order.STATUS_CHOICES,
        'payment_status_choices': Payment.STATUS_CHOICES,
    }
    return render(request, 'adminpanel/manage_orders.html', context)


@login_required(login_url='login')
@admin_required
def order_detail(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    payment = order.payments.order_by('-created_at').first() if hasattr(order, 'payments') else None
    delivery_time = order.order_date if order.status in {'delivered', 'picked_up', 'out_for_delivery'} else None
    return render(request, 'adminpanel/order_detail.html', {
        'order': order,
        'payment': payment,
        'delivery_time': delivery_time,
        'order_status_choices': Order.STATUS_CHOICES,
        'payment_status_choices': Payment.STATUS_CHOICES,
    })


@login_required(login_url='login')
@admin_required
def update_order_status(request, order_id):
    if request.method == 'POST':
        order = get_object_or_404(Order, id=order_id)
        new_status = request.POST.get('status')
        if new_status in [choice[0] for choice in Order.STATUS_CHOICES]:
            try:
                transition_order_status(order, new_status, allow_any=True)
                messages.success(request, f'Order #{order.id} status updated successfully.')
            except ValueError as exc:
                messages.error(str(exc))
        else:
            messages.error(request, 'Invalid order status.')
    return redirect('adminpanel:order_detail', order_id=order_id)


@login_required(login_url='login')
@admin_required
def cancel_order(request, order_id):
    if request.method == 'POST':
        order = get_object_or_404(Order, id=order_id)
        try:
            transition_order_status(order, 'cancelled', allow_any=True)
            messages.success(request, f'Order #{order.id} cancelled successfully.')
        except ValueError as exc:
            messages.error(str(exc))
    return redirect('adminpanel:order_detail', order_id=order_id)


@login_required(login_url='login')
@admin_required
def manage_subscriptions(request):
    queryset = Subscription.objects.select_related('student', 'mess', 'mess__vendor').order_by('-start_date', '-id')
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()

    if query:
        queryset = queryset.filter(
            Q(id__icontains=query) |
            Q(student__username__icontains=query) |
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(mess__mess_name__icontains=query) |
            Q(mess__vendor__username__icontains=query)
        )
    if status:
        queryset = queryset.filter(status=status)

    paginator = Paginator(queryset, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    for subscription in page_obj:
        payment = Payment.objects.filter(subscription=subscription).order_by('-created_at').first()
        subscription.payment = payment
        subscription.payment_status = payment.get_status_display() if payment else 'N/A'
        subscription.payment_status_value = payment.status if payment else 'n/a'
        subscription.payment_method = payment.payment_method if payment else 'N/A'
        subscription.payment_amount = payment.amount if payment else subscription.price_paid

    context = {
        'page_obj': page_obj,
        'query': query,
        'status': status,
        'status_choices': [('pending', 'Pending')] + list(Subscription.STATUS_CHOICES),
    }
    return render(request, 'adminpanel/manage_subscriptions.html', context)


@login_required(login_url='login')
@admin_required
def subscription_detail(request, subscription_id):
    subscription = get_object_or_404(Subscription, id=subscription_id)
    payment = Payment.objects.filter(subscription=subscription).order_by('-created_at').first()
    return render(request, 'adminpanel/subscription_detail.html', {
        'subscription': subscription,
        'payment': payment,
        'status_choices': [('pending', 'Pending')] + list(Subscription.STATUS_CHOICES),
    })


@login_required(login_url='login')
@admin_required
def activate_subscription(request, subscription_id):
    if request.method == 'POST':
        subscription = get_object_or_404(Subscription, id=subscription_id)
        subscription.status = 'active'
        if subscription.end_date and subscription.end_date < date.today():
            subscription.end_date = date.today() + timedelta(days=30)
        subscription.save()
        messages.success(request, f'Subscription #{subscription.id} activated successfully.')
    return redirect('adminpanel:subscription_detail', subscription_id=subscription_id)


@login_required(login_url='login')
@admin_required
def pause_subscription(request, subscription_id):
    if request.method == 'POST':
        subscription = get_object_or_404(Subscription, id=subscription_id)
        subscription.status = 'paused'
        subscription.save()
        messages.success(request, f'Subscription #{subscription.id} paused successfully.')
    return redirect('adminpanel:subscription_detail', subscription_id=subscription_id)


@login_required(login_url='login')
@admin_required
def resume_subscription(request, subscription_id):
    if request.method == 'POST':
        subscription = get_object_or_404(Subscription, id=subscription_id)
        subscription.status = 'active'
        subscription.save()
        messages.success(request, f'Subscription #{subscription.id} resumed successfully.')
    return redirect('adminpanel:subscription_detail', subscription_id=subscription_id)


@login_required(login_url='login')
@admin_required
def cancel_subscription(request, subscription_id):
    if request.method == 'POST':
        subscription = get_object_or_404(Subscription, id=subscription_id)
        subscription.status = 'cancelled'
        subscription.save()
        messages.success(request, f'Subscription #{subscription.id} cancelled successfully.')
    return redirect('adminpanel:subscription_detail', subscription_id=subscription_id)


@login_required(login_url='login')
@admin_required
def extend_subscription(request, subscription_id):
    if request.method == 'POST':
        subscription = get_object_or_404(Subscription, id=subscription_id)
        base_date = subscription.end_date or date.today()
        subscription.end_date = max(base_date, date.today()) + timedelta(days=30)
        if subscription.status in {'cancelled', 'expired'}:
            subscription.status = 'active'
        subscription.save()
        messages.success(request, f'Subscription #{subscription.id} extended successfully.')
    return redirect('adminpanel:subscription_detail', subscription_id=subscription_id)


@login_required(login_url='login')
@admin_required
def manage_complaints(request):
    queryset = Complaint.objects.select_related('student', 'mess', 'mess__vendor').order_by('-created_at')
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()

    if query:
        queryset = queryset.filter(
            Q(id__icontains=query) |
            Q(student__username__icontains=query) |
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(mess__mess_name__icontains=query) |
            Q(mess__vendor__username__icontains=query) |
            Q(mess__vendor__first_name__icontains=query) |
            Q(mess__vendor__last_name__icontains=query)
        )
    if status:
        queryset = queryset.filter(status=status)

    paginator = Paginator(queryset, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'query': query,
        'status': status,
        'status_choices': [('pending', 'Pending')] + list(Complaint.STATUS_CHOICES),
        'category_choices': Complaint.CATEGORY_CHOICES,
    }
    return render(request, 'adminpanel/manage_complaints.html', context)


@login_required(login_url='login')
@admin_required
def complaint_detail(request, complaint_id):
    complaint = get_object_or_404(Complaint, id=complaint_id)
    return render(request, 'adminpanel/complaint_detail.html', {
        'complaint': complaint,
        'status_choices': [('pending', 'Pending')] + list(Complaint.STATUS_CHOICES),
        'category_choices': Complaint.CATEGORY_CHOICES,
    })


@login_required(login_url='login')
@admin_required
def update_complaint_status(request, complaint_id):
    if request.method == 'POST':
        complaint = get_object_or_404(Complaint, id=complaint_id)
        new_status = request.POST.get('status')
        if new_status in [choice[0] for choice in Complaint.STATUS_CHOICES]:
            complaint.status = new_status
            complaint.save()
            if complaint.student and complaint.student.phone:
                send_sms(
                    complaint.student.phone,
                    f"Your complaint #{complaint.id} status has been updated to {complaint.get_status_display()}."
                )
            messages.success(request, f'Complaint #{complaint.id} status updated successfully.')
        else:
            messages.error(request, 'Invalid complaint status.')
    return redirect('adminpanel:complaint_detail', complaint_id=complaint_id)


@login_required(login_url='login')
@admin_required
def resolve_complaint(request, complaint_id):
    if request.method == 'POST':
        complaint = get_object_or_404(Complaint, id=complaint_id)
        complaint.status = 'resolved'
        complaint.response = request.POST.get('response', complaint.response or '')
        complaint.save()
        if complaint.student and complaint.student.email:
            send_complaint_resolution_email(
                complaint.student.username,
                complaint.student.email,
                complaint.id,
                complaint.response,
            )
        if settings.DEFAULT_FROM_EMAIL:
            send_admin_notification(
                settings.DEFAULT_FROM_EMAIL,
                'Complaint resolved',
                f"Complaint #{complaint.id} was resolved with response: {complaint.response}",
                category='admin_complaint_resolved',
            )
        if complaint.student and complaint.student.phone:
            send_sms(
                complaint.student.phone,
                f"Your complaint #{complaint.id} has been resolved."
            )
        if complaint.student:
            send_push_notification(
                complaint.student,
                'Complaint reply',
                f"Your complaint #{complaint.id} has been resolved."
            )
        messages.success(request, f'Complaint #{complaint.id} resolved successfully.')
    return redirect('adminpanel:complaint_detail', complaint_id=complaint_id)


@login_required(login_url='login')
@admin_required
def close_complaint(request, complaint_id):
    if request.method == 'POST':
        complaint = get_object_or_404(Complaint, id=complaint_id)
        complaint.status = 'resolved'
        complaint.response = request.POST.get('response', complaint.response or '')
        complaint.save()
        if complaint.student and complaint.student.email:
            send_complaint_resolution_email(
                complaint.student.username,
                complaint.student.email,
                complaint.id,
                complaint.response,
            )
        if settings.DEFAULT_FROM_EMAIL:
            send_admin_notification(
                settings.DEFAULT_FROM_EMAIL,
                'Complaint closed',
                f"Complaint #{complaint.id} was closed with response: {complaint.response}",
                category='admin_complaint_closed',
            )
        if complaint.student and complaint.student.phone:
            send_sms(
                complaint.student.phone,
                f"Your complaint #{complaint.id} has been closed."
            )
        if complaint.student:
            send_push_notification(
                complaint.student,
                'Complaint reply',
                f"Your complaint #{complaint.id} has been closed."
            )
        messages.success(request, f'Complaint #{complaint.id} closed successfully.')
    return redirect('adminpanel:complaint_detail', complaint_id=complaint_id)


@login_required(login_url='login')
@admin_required
def ai_insights(request):
    orders = Order.objects.select_related('student', 'mess').prefetch_related('items__meal').all()
    complaints = Complaint.objects.select_related('student', 'mess').all()
    successful_payments = Payment.objects.filter(status='success')
    meals = Meal.objects.filter(is_available=True).select_related('mess')

    meal_counts = {}
    meal_price_map = {meal.id: float(meal.price) for meal in meals}
    for order in orders:
        for item in order.items.all():
            meal_counts[item.meal.name] = meal_counts.get(item.meal.name, 0) + item.quantity

    most_popular_meal = max(meal_counts.items(), key=lambda item: item[1])[0] if meal_counts else 'No data'
    least_popular_meal = min(meal_counts.items(), key=lambda item: item[1])[0] if meal_counts else 'No data'

    hours = [order.order_date.hour for order in orders if order.order_date]
    peak_order_hour = f"{max(set(hours), key=hours.count):02d}:00" if hours else '12:00'

    vendor_order_counts = {}
    for order in orders:
        vendor_name = order.mess.vendor.username if order.mess and order.mess.vendor else 'Unknown'
        vendor_order_counts[vendor_name] = vendor_order_counts.get(vendor_name, 0) + 1
    top_vendor = max(vendor_order_counts.items(), key=lambda item: item[1])[0] if vendor_order_counts else 'No data'

    revenue_summary = successful_payments.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    complaint_summary = {
        'open': complaints.filter(status='open').count(),
        'resolved': complaints.filter(status='resolved').count(),
        'total': complaints.count(),
    }

    predictions = predict_meal_demands([meal.id for meal in meals])
    predicted_tomorrow_orders = sum(item['tomorrow'] for item in predictions)
    predicted_weekly_revenue = sum(item['weekly'] * meal_price_map.get(item['meal_id'], 0) for item in predictions)

    high_demand_meals = [
        {'meal_name': item['meal_name'], 'tomorrow': item['tomorrow']}
        for item in sorted(predictions, key=lambda entry: entry['tomorrow'], reverse=True)[:5]
    ]
    low_demand_meals = [
        {'meal_name': item['meal_name'], 'tomorrow': item['tomorrow']}
        for item in sorted(predictions, key=lambda entry: entry['tomorrow'])[:5]
    ]

    complaint_labels = ['Open', 'Resolved', 'Total']
    complaint_values = [complaint_summary['open'], complaint_summary['resolved'], complaint_summary['total']]
    demand_labels = [item['meal_name'] for item in high_demand_meals] or ['No data']
    demand_values = [item['tomorrow'] for item in high_demand_meals] or [0]

    insights = get_ai_insights('admin')

    context = {
        'most_popular_meal': most_popular_meal,
        'least_popular_meal': least_popular_meal,
        'peak_order_hour': peak_order_hour,
        'top_vendor': top_vendor,
        'revenue_summary': revenue_summary,
        'complaint_summary': complaint_summary,
        'predicted_tomorrow_orders': predicted_tomorrow_orders,
        'predicted_weekly_revenue': predicted_weekly_revenue,
        'high_demand_meals': high_demand_meals,
        'low_demand_meals': low_demand_meals,
        'complaint_labels': complaint_labels,
        'complaint_values': complaint_values,
        'demand_labels': demand_labels,
        'demand_values': demand_values,
        'insights': insights,
    }
    return render(request, 'adminpanel/ai_insights.html', context)


@login_required(login_url='login')
@admin_required
def analytics_dashboard(request):
    now = timezone.now()
    range_filter = request.GET.get('range', 'this_month')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    start_dt = None
    end_dt = None

    if start_date and end_date:
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            start_dt = None
            end_dt = None

    if start_dt and end_dt:
        queryset = Order.objects.filter(order_date__date__range=[start_dt, end_dt])
        payment_queryset = Payment.objects.filter(created_at__date__range=[start_dt, end_dt])
        student_queryset = User.objects.filter(date_joined__date__range=[start_dt, end_dt], role='student')
        vendor_queryset = User.objects.filter(date_joined__date__range=[start_dt, end_dt], role='vendor')
        complaint_queryset = Complaint.objects.filter(created_at__date__range=[start_dt, end_dt])
        subscription_queryset = Subscription.objects.filter(start_date__range=[start_dt, end_dt])
    else:
        if range_filter == 'today':
            start_dt = now.date()
            end_dt = now.date()
        elif range_filter == 'last_7_days':
            start_dt = (now - timedelta(days=6)).date()
            end_dt = now.date()
        elif range_filter == 'last_30_days':
            start_dt = (now - timedelta(days=29)).date()
            end_dt = now.date()
        elif range_filter == 'this_year':
            start_dt = date(now.year, 1, 1)
            end_dt = date(now.year, 12, 31)
        else:
            start_dt = date(now.year, now.month, 1)
            end_dt = date(now.year, now.month, 1) + timedelta(days=32)
            end_dt = date(end_dt.year, end_dt.month, 1) - timedelta(days=1)

        queryset = Order.objects.filter(order_date__date__range=[start_dt, end_dt])
        payment_queryset = Payment.objects.filter(created_at__date__range=[start_dt, end_dt])
        student_queryset = User.objects.filter(date_joined__date__range=[start_dt, end_dt], role='student')
        vendor_queryset = User.objects.filter(date_joined__date__range=[start_dt, end_dt], role='vendor')
        complaint_queryset = Complaint.objects.filter(created_at__date__range=[start_dt, end_dt])
        subscription_queryset = Subscription.objects.filter(start_date__range=[start_dt, end_dt])

    total_revenue = payment_queryset.filter(status='success').aggregate(total=Sum('amount'))['total'] or Decimal('0')
    total_students = User.objects.filter(role='student').count()
    total_vendors = User.objects.filter(role='vendor').count()
    total_messes = Mess.objects.count()
    total_orders = queryset.count()
    active_subscriptions = Subscription.objects.filter(status='active').count()
    pending_complaints = Complaint.objects.filter(status='open').count()
    wallet_summary = WalletTransaction.objects.aggregate(total=Sum('amount'))['total'] or Decimal('0')

    revenue_series = []
    orders_series = []
    student_series = []
    vendor_series = []
    complaint_series = []
    subscription_series = []

    labels = []
    current = start_dt
    while current <= end_dt:
        labels.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)

    for label in labels:
        day = datetime.strptime(label, '%Y-%m-%d').date()
        revenue_series.append(float(payment_queryset.filter(created_at__date=day, status='success').aggregate(total=Sum('amount'))['total'] or 0))
        orders_series.append(queryset.filter(order_date__date=day).count())
        student_series.append(student_queryset.filter(date_joined__date=day).count())
        vendor_series.append(vendor_queryset.filter(date_joined__date=day).count())
        complaint_series.append(complaint_queryset.filter(created_at__date=day).count())
        subscription_series.append(subscription_queryset.filter(start_date=day).count())

    top_meals = (
        OrderItem.objects.values('meal__name')
        .annotate(total_orders=Sum('quantity'))
        .order_by('-total_orders')[:10]
    )
    top_messes = (
        Order.objects.values('mess__mess_name')
        .annotate(total_orders=Count('id'))
        .order_by('-total_orders')[:10]
    )
    top_students = (
        Order.objects.values('student__username')
        .annotate(total_orders=Count('id'))
        .order_by('-total_orders')[:10]
    )
    top_vendors = (
        Payment.objects.filter(status='success').values('order__mess__vendor__username')
        .annotate(total_revenue=Sum('amount'))
        .order_by('-total_revenue')[:10]
    )
    complaint_status_counts = {
        'open': Complaint.objects.filter(status='open').count(),
        'in_progress': Complaint.objects.filter(status='in_progress').count(),
        'resolved': Complaint.objects.filter(status='resolved').count(),
    }
    subscription_status_counts = {
        'active': Subscription.objects.filter(status='active').count(),
        'paused': Subscription.objects.filter(status='paused').count(),
        'cancelled': Subscription.objects.filter(status='cancelled').count(),
        'expired': Subscription.objects.filter(status='expired').count(),
    }

    context = {
        'total_revenue': total_revenue,
        'total_students': total_students,
        'total_vendors': total_vendors,
        'total_messes': total_messes,
        'total_orders': total_orders,
        'active_subscriptions': active_subscriptions,
        'pending_complaints': pending_complaints,
        'wallet_summary': wallet_summary,
        'range_filter': range_filter,
        'start_date': start_date,
        'end_date': end_date,
        'labels': labels,
        'revenue_series': revenue_series,
        'orders_series': orders_series,
        'student_series': student_series,
        'vendor_series': vendor_series,
        'complaint_series': complaint_series,
        'subscription_series': subscription_series,
        'top_meals': top_meals,
        'top_messes': top_messes,
        'top_students': top_students,
        'top_vendors': top_vendors,
        'complaint_status_counts': complaint_status_counts,
        'subscription_status_counts': subscription_status_counts,
    }
    return render(request, 'adminpanel/analytics.html', context)


@login_required(login_url='login')
@admin_required
def export_analytics_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="analytics.csv"'
    writer = csv.writer(response)
    writer.writerow(['Metric', 'Value'])
    writer.writerow(['Total Revenue', request.GET.get('total_revenue', '')])
    writer.writerow(['Total Students', request.GET.get('total_students', '')])
    writer.writerow(['Total Vendors', request.GET.get('total_vendors', '')])
    writer.writerow(['Total Messes', request.GET.get('total_messes', '')])
    writer.writerow(['Total Orders', request.GET.get('total_orders', '')])
    writer.writerow(['Active Subscriptions', request.GET.get('active_subscriptions', '')])
    writer.writerow(['Pending Complaints', request.GET.get('pending_complaints', '')])
    writer.writerow(['Wallet Summary', request.GET.get('wallet_summary', '')])
    return response


@login_required(login_url='login')
@admin_required
def export_analytics_excel(request):
    response = HttpResponse(content_type='application/vnd.ms-excel')
    response['Content-Disposition'] = 'attachment; filename="analytics.xls"'
    response.write('Metric\tValue\n')
    response.write(f'Total Revenue\t{request.GET.get("total_revenue", "")}\n')
    response.write(f'Total Students\t{request.GET.get("total_students", "")}\n')
    response.write(f'Total Vendors\t{request.GET.get("total_vendors", "")}\n')
    response.write(f'Total Messes\t{request.GET.get("total_messes", "")}\n')
    response.write(f'Total Orders\t{request.GET.get("total_orders", "")}\n')
    response.write(f'Active Subscriptions\t{request.GET.get("active_subscriptions", "")}\n')
    response.write(f'Pending Complaints\t{request.GET.get("pending_complaints", "")}\n')
    response.write(f'Wallet Summary\t{request.GET.get("wallet_summary", "")}\n')
    return response


@login_required(login_url='login')
@admin_required
def manage_vendors(request):
    queryset = User.objects.filter(role='vendor').select_related('vendor_profile').order_by('-date_joined')
    query = request.GET.get('q', '').strip()

    if query:
        queryset = queryset.filter(
            Q(username__icontains=query) |
            Q(email__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(vendor_profile__business_name__icontains=query) |
            Q(messes__mess_name__icontains=query)
        ).distinct()

    paginator = Paginator(queryset, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'adminpanel/manage_vendors.html', {
        'page_obj': page_obj,
        'query': query,
    })


@login_required(login_url='login')
@admin_required
def toggle_vendor_status(request, user_id):
    if request.method == 'POST':
        vendor = get_object_or_404(User, id=user_id, role='vendor')
        vendor.is_active = not vendor.is_active
        vendor.save()
        action = 'unblocked' if vendor.is_active else 'blocked'
        messages.success(request, f'Vendor {vendor.username} {action} successfully.')
    return redirect('adminpanel:manage_vendors')


@login_required(login_url='login')
@admin_required
def approve_vendor(request, user_id):
    if request.method == 'POST':
        vendor = get_object_or_404(User, id=user_id, role='vendor')
        profile = vendor.vendor_profile
        profile.verification_status = 'approved'
        profile.save()
        if vendor.email:
            send_vendor_notification(
                vendor.username,
                vendor.email,
                'Vendor approval update',
                'Your vendor account has been approved by the admin. You can now manage your messes.',
                category='vendor_approval',
            )
        messages.success(request, f'Vendor {vendor.username} approved successfully.')
    return redirect('adminpanel:manage_vendors')


@login_required(login_url='login')
@admin_required
def reject_vendor(request, user_id):
    if request.method == 'POST':
        vendor = get_object_or_404(User, id=user_id, role='vendor')
        profile = vendor.vendor_profile
        profile.verification_status = 'rejected'
        profile.save()
        if vendor.email:
            send_vendor_notification(
                vendor.username,
                vendor.email,
                'Vendor approval update',
                'Your vendor account has been rejected by the admin. Please contact support for more details.',
                category='vendor_rejection',
            )
        messages.success(request, f'Vendor {vendor.username} rejected successfully.')
    return redirect('adminpanel:manage_vendors')


@login_required(login_url='login')
@admin_required
def vendor_profile(request, user_id):
    vendor = get_object_or_404(User, id=user_id, role='vendor')
    profile = getattr(vendor, 'vendor_profile', None)
    messes = vendor.messes.all() if hasattr(vendor, 'messes') else []
    return render(request, 'adminpanel/vendor_profile.html', {
        'vendor': vendor,
        'profile': profile,
        'messes': messes,
    })


@login_required(login_url='login')
@admin_required
def manage_delivery_boys(request):
    queryset = User.objects.filter(role='delivery').select_related('delivery_profile').order_by('-date_joined')
    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    availability_filter = request.GET.get('availability', '').strip()

    if query:
        queryset = queryset.filter(
            Q(username__icontains=query) |
            Q(email__icontains=query) |
            Q(phone__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(delivery_profile__vehicle_number__icontains=query) |
            Q(delivery_profile__license_number__icontains=query)
        ).distinct()

    if status_filter:
        if status_filter == 'approved':
            queryset = queryset.filter(delivery_profile__verification_status='approved')
        elif status_filter == 'pending':
            queryset = queryset.filter(delivery_profile__verification_status='pending')
        elif status_filter == 'rejected':
            queryset = queryset.filter(delivery_profile__verification_status='rejected')

    if availability_filter:
        queryset = queryset.filter(delivery_profile__availability_status=availability_filter)

    delivery_boys = []
    for delivery_boy in queryset:
        metrics = get_delivery_boy_metrics(delivery_boy)
        delivery_boys.append({
            'delivery_boy': delivery_boy,
            'profile': metrics['profile'],
            'active_deliveries': metrics['active_deliveries'],
            'completed_deliveries': metrics['completed_deliveries'],
            'pending_deliveries': metrics['pending_deliveries'],
            'total_deliveries': metrics['total_deliveries'],
        })

    paginator = Paginator(delivery_boys, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'adminpanel/manage_delivery_boys.html', {
        'page_obj': page_obj,
        'query': query,
        'status': status_filter,
        'availability': availability_filter,
    })


@login_required(login_url='login')
@admin_required
def toggle_delivery_boy_status(request, user_id):
    if request.method == 'POST':
        delivery_boy = get_object_or_404(User, id=user_id, role='delivery')
        delivery_boy.is_active = not delivery_boy.is_active
        delivery_boy.save()
        action = 'unblocked' if delivery_boy.is_active else 'blocked'
        messages.success(request, f'Delivery Boy {delivery_boy.username} {action} successfully.')
    return redirect('adminpanel:manage_delivery_boys')


@login_required(login_url='login')
@admin_required
def approve_delivery_boy(request, user_id):
    if request.method == 'POST':
        delivery_boy = get_object_or_404(User, id=user_id, role='delivery')
        profile = delivery_boy.delivery_profile
        profile.verification_status = 'approved'
        if profile.availability_status in ['offline', 'busy']:
            profile.availability_status = 'available'
        profile.save(update_fields=['verification_status', 'availability_status'])
        messages.success(request, f'Delivery Boy {delivery_boy.username} approved successfully.')
    return redirect('adminpanel:manage_delivery_boys')


@login_required(login_url='login')
@admin_required
def reject_delivery_boy(request, user_id):
    if request.method == 'POST':
        delivery_boy = get_object_or_404(User, id=user_id, role='delivery')
        profile = delivery_boy.delivery_profile
        profile.verification_status = 'rejected'
        profile.save()
        messages.success(request, f'Delivery Boy {delivery_boy.username} rejected successfully.')
    return redirect('adminpanel:manage_delivery_boys')


@login_required(login_url='login')
@admin_required
def delivery_boy_profile(request, user_id):
    delivery_boy = get_object_or_404(User, id=user_id, role='delivery')
    profile = getattr(delivery_boy, 'delivery_profile', None)
    assigned_orders = Order.objects.filter(delivery_boy=delivery_boy).order_by('-order_date')[:10]
    return render(request, 'adminpanel/delivery_boy_profile.html', {
        'delivery_boy': delivery_boy,
        'profile': profile,
        'assigned_orders': assigned_orders,
    })
