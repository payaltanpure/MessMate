from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import User, StudentProfile, VendorProfile
from student.models import Complaint, Order, Payment, Subscription
from vendor.models import Mess, Meal
from .forms import MealAdminForm, MessAdminForm


def admin_required(view_func):
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_authenticated and (request.user.role == 'admin' or request.user.is_superuser):
            return view_func(request, *args, **kwargs)
        messages.error(request, 'Access Denied. Admins only.')
        return redirect('home')

    return _wrapped_view


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
    })


@login_required(login_url='login')
@admin_required
def mess_detail(request, mess_id):
    mess = get_object_or_404(Mess, id=mess_id)
    meals = mess.meals.all().order_by('meal_type', 'name')
    active_subscriptions = Subscription.objects.filter(mess=mess, status='active').count()
    return render(request, 'adminpanel/mess_detail.html', {
        'mess': mess,
        'meals': meals,
        'active_subscriptions': active_subscriptions,
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
