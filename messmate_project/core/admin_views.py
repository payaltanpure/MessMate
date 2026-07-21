from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count
from django.db.models.functions import TruncDate
from django.conf import settings

from core.email_services import send_admin_notification, send_critical_alert_email, send_daily_report_email

from accounts.models import User, VendorProfile, DeliveryBoyProfile
from student.models import Order, Subscription, Payment, Complaint
import json
import datetime

@login_required(login_url='login')
def admin_dashboard(request):
    """
    Custom Admin Dashboard displaying revenue trends, subscription counts,
    vendor approvals, and complaints management.
    """
    # Restrict to superuser or admin role
    if not request.user.is_superuser and request.user.role != 'admin':
        messages.error(request, "Access Denied. Admins only.")
        return redirect('login')

    # Platform Analytics Metrics
    total_users = User.objects.count()
    total_vendors = User.objects.filter(role='vendor').count()
    total_orders = Order.objects.count()
    total_revenue = Payment.objects.filter(status='success').aggregate(Sum('amount'))['amount__sum'] or 0.00

    # Verification queues
    pending_vendors = VendorProfile.objects.filter(verification_status='pending')
    all_vendors = VendorProfile.objects.all().order_by('-verification_status')
    delivery_staff = DeliveryBoyProfile.objects.all()

    # Active/unresolved complaints
    complaints = Complaint.objects.filter(status__in=['open', 'in_progress']).order_by('-created_at')

    # Chart 1: Revenue Graph (Last 7 days)
    seven_days_ago = timezone_now() - datetime.timedelta(days=7)
    revenue_trend = Payment.objects.filter(
        status='success', 
        created_at__gte=seven_days_ago
    ).annotate(date=TruncDate('created_at')).values('date').annotate(total=Sum('amount')).order_by('date')

    revenue_labels = [item['date'].strftime('%Y-%m-%d') for item in revenue_trend]
    revenue_values = [float(item['total']) for item in revenue_trend]

    # Chart 2: Orders Graph (Last 7 days)
    order_trend = Order.objects.filter(
        order_date__gte=seven_days_ago
    ).annotate(date=TruncDate('order_date')).values('date').annotate(count=Count('id')).order_by('date')

    order_labels = [item['date'].strftime('%Y-%m-%d') for item in order_trend]
    order_values = [item['count'] for item in order_trend]

    # Chart 3: Active Subscriptions Count
    active_subs = Subscription.objects.filter(status='active').count()
    paused_subs = Subscription.objects.filter(status='paused').count()
    expired_subs = Subscription.objects.filter(status='expired').count()

    if settings.DEFAULT_FROM_EMAIL:
        send_daily_report_email(
            settings.DEFAULT_FROM_EMAIL,
            f"SMARTMESS AI daily summary\nUsers: {total_users}\nVendors: {total_vendors}\nOrders: {total_orders}\nRevenue: {total_revenue}",
            category='daily_report',
        )

    if complaints.exists() and settings.DEFAULT_FROM_EMAIL:
        send_critical_alert_email(
            settings.DEFAULT_FROM_EMAIL,
            f"There are {complaints.count()} active complaints pending review.",
            category='critical_alert',
        )

    context = {
        'total_users': total_users,
        'total_vendors': total_vendors,
        'total_orders': total_orders,
        'total_revenue': float(total_revenue),
        'pending_vendors': pending_vendors,
        'all_vendors': all_vendors,
        'delivery_staff': delivery_staff,
        'complaints': complaints,
        
        # Serialized JSON for Chart.js
        'revenue_labels': json.dumps(revenue_labels),
        'revenue_values': json.dumps(revenue_values),
        'order_labels': json.dumps(order_labels),
        'order_values': json.dumps(order_values),
        'sub_pie_data': json.dumps([active_subs, paused_subs, expired_subs]),
    }
    return render(request, 'admin_dashboard/dashboard.html', context)


@login_required(login_url='login')
def approve_vendor(request, profile_id):
    if not request.user.is_superuser and request.user.role != 'admin':
        return redirect('login')
    profile = get_object_or_404(VendorProfile, id=profile_id)
    profile.verification_status = 'approved'
    profile.save()
    if profile.user and profile.user.email:
        send_admin_notification(
            profile.user.email,
            'Vendor approved',
            'Your vendor registration has been approved by the admin.',
            category='vendor_registration',
        )
    messages.success(request, f"Vendor '{profile.business_name}' approved successfully!")
    return redirect('admin_dashboard')


@login_required(login_url='login')
def reject_vendor(request, profile_id):
    if not request.user.is_superuser and request.user.role != 'admin':
        return redirect('login')
    profile = get_object_or_404(VendorProfile, id=profile_id)
    profile.verification_status = 'rejected'
    profile.save()
    if profile.user and profile.user.email:
        send_admin_notification(
            profile.user.email,
            'Vendor registration update',
            'Your vendor registration was rejected by the admin. Please contact support for details.',
            category='vendor_registration',
        )
    messages.warning(request, f"Vendor '{profile.business_name}' verification rejected.")
    return redirect('admin_dashboard')


@login_required(login_url='login')
def suspend_vendor(request, profile_id):
    if not request.user.is_superuser and request.user.role != 'admin':
        return redirect('login')
    profile = get_object_or_404(VendorProfile, id=profile_id)
    profile.verification_status = 'suspended'
    profile.save()
    messages.error(request, f"Vendor '{profile.business_name}' has been suspended.")
    return redirect('admin_dashboard')


@login_required(login_url='login')
def admin_respond_complaint(request, complaint_id):
    if not request.user.is_superuser and request.user.role != 'admin':
        return redirect('login')
    complaint = get_object_or_404(Complaint, id=complaint_id)
    if request.method == "POST":
        response = request.POST.get('response')
        complaint.response = f"[Admin response]: {response}"
        complaint.status = 'resolved'
        complaint.save()
        messages.success(request, f"Complaint #{complaint.id} resolved by Admin.")
    return redirect('admin_dashboard')


def timezone_now():
    return datetime.datetime.now()
