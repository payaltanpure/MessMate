from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from student.models import Order, Notification
from accounts.models import DeliveryBoyProfile


VALID_DELIVERY_STATUS_FLOW = {
    'accepted': {'pending'},
    'preparing': {'accepted'},
    'ready_for_pickup': {'preparing', 'assigned'},
    'assigned': {'ready_for_pickup'},
    'picked_up': {'assigned'},
    'out_for_delivery': {'assigned', 'picked_up'},
    'delivered': {'out_for_delivery'},
    'completed': {'delivered'},
    'cancelled': {'pending', 'accepted', 'preparing', 'ready_for_pickup', 'assigned', 'picked_up', 'out_for_delivery', 'delivered', 'completed'},
}


def set_delivery_boy_availability(delivery_boy, available):
    """Update delivery-boy availability using the existing profile model."""
    profile, _ = DeliveryBoyProfile.objects.get_or_create(user=delivery_boy)
    profile.availability_status = 'available' if available else 'busy'
    profile.save(update_fields=['availability_status'])
    return profile


def assign_order_to_delivery_boy(order, delivery_boy, status='preparing'):
    """Assign a delivery boy to an order and update the order state consistently."""
    order.delivery_boy = delivery_boy
    order.status = status
    order.assigned_at = timezone.now()
    order.save(update_fields=['delivery_boy', 'status', 'assigned_at'])
    set_delivery_boy_availability(delivery_boy, False)
    return order


def can_reassign_delivery(order):
    """Allow reassignment only while the order has not been picked up by the assigned delivery boy."""
    return order.status in ['ready_for_pickup', 'assigned']


def get_delivery_boy_metrics(delivery_boy):
    """Return shared delivery metrics for a delivery boy based on the existing Order model."""
    profile, _ = DeliveryBoyProfile.objects.get_or_create(user=delivery_boy)
    orders = Order.objects.filter(delivery_boy=delivery_boy)
    active_orders = orders.filter(status__in=['assigned', 'picked_up', 'out_for_delivery'])
    active_deliveries = orders.filter(status__in=['picked_up', 'out_for_delivery'])
    completed_deliveries = orders.filter(status__in=['delivered', 'completed'])
    pending_deliveries = orders.filter(status='assigned')

    return {
        'profile': profile,
        'assigned_orders': active_orders.count(),
        'active_deliveries': active_deliveries.count(),
        'completed_deliveries': completed_deliveries.count(),
        'pending_deliveries': pending_deliveries.count(),
        'total_deliveries': orders.count(),
    }


def transition_order_status(order, new_status, allow_any=False):
    """Advance an order through the shared delivery workflow."""
    valid_statuses = {value for value, _ in Order.STATUS_CHOICES}
    if new_status not in valid_statuses:
        raise ValueError(f'Invalid status: {new_status}')

    if order.status == new_status:
        return order

    if allow_any:
        order.status = new_status
        order.save(update_fields=['status'])
        return order

    allowed_previous = VALID_DELIVERY_STATUS_FLOW.get(new_status, set())
    if order.status not in allowed_previous:
        raise ValueError(f'Cannot move order #{order.id} from {order.status} to {new_status}')

    order.status = new_status
    order.save(update_fields=['status'])
    return order

@login_required(login_url='login')
def delivery_dashboard(request):
    """
    Dashboard for delivery staff showing assigned orders, pickup pool, and delivery verification.
    """
    if request.user.role != 'delivery':
        messages.error(request, "Access Denied. Delivery staff only.")
        return redirect('login')

    db_profile, _ = DeliveryBoyProfile.objects.get_or_create(user=request.user)

    assigned_orders = Order.objects.filter(
        delivery_boy=request.user,
        status__in=['assigned', 'picked_up', 'out_for_delivery']
    ).order_by('-order_date')

    my_deliveries = assigned_orders
    new_assignments = assigned_orders.filter(status='assigned')
    active_deliveries = assigned_orders.filter(status__in=['picked_up', 'out_for_delivery'])

    completed_deliveries = Order.objects.filter(
        delivery_boy=request.user,
        status__in=['delivered', 'completed']
    ).order_by('-order_date')[:10]

    pending_deliveries = Order.objects.filter(
        delivery_boy=request.user,
        status='assigned'
    ).count()
    todays_deliveries = Order.objects.filter(
        delivery_boy=request.user,
        status='delivered',
        order_date__date=timezone.now().date()
    ).count()
    cancelled_deliveries = Order.objects.filter(
        delivery_boy=request.user,
        status='cancelled'
    ).count()
    rejected_deliveries = Order.objects.filter(
        delivery_boy__isnull=True,
        status='ready_for_pickup'
    ).count()
    assigned_orders_count = assigned_orders.count()
    recent_orders = Order.objects.filter(
        delivery_boy=request.user
    ).order_by('-order_date')[:8]
    total_deliveries = Order.objects.filter(delivery_boy=request.user).count()
    accepted_assignments = Order.objects.filter(delivery_boy=request.user).exclude(status='ready_for_pickup').count()
    acceptance_rate = round((accepted_assignments / total_deliveries * 100), 1) if total_deliveries else 0
    completion_rate = round((completed_deliveries.count() / total_deliveries * 100), 1) if total_deliveries else 0

    performance_summary = {
        'assigned': assigned_orders_count,
        'completed': completed_deliveries.count(),
        'pending': pending_deliveries,
        'cancelled': cancelled_deliveries,
        'acceptance_rate': acceptance_rate,
        'completion_rate': completion_rate,
    }

    context = {
        'profile': db_profile,
        'my_deliveries': my_deliveries,
        'assigned_orders': assigned_orders,
        'new_assignments': new_assignments,
        'active_deliveries': active_deliveries,
        'completed_deliveries': completed_deliveries,
        'pending_deliveries': pending_deliveries,
        'todays_deliveries': todays_deliveries,
        'cancelled_deliveries': cancelled_deliveries,
        'rejected_deliveries': rejected_deliveries,
        'recent_orders': recent_orders,
        'performance_summary': performance_summary,
    }
    return render(request, 'delivery/dashboard.html', context)


@login_required(login_url='login')
def delivery_profile(request):
    """Show and update the delivery boy profile details."""
    if request.user.role != 'delivery':
        messages.error(request, "Access Denied. Delivery staff only.")
        return redirect('login')

    profile, _ = DeliveryBoyProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        phone = request.POST.get('phone', '').strip()
        if phone:
            request.user.phone = phone
            request.user.save(update_fields=['phone'])

        profile.vehicle_type = request.POST.get('vehicle_type', profile.vehicle_type)
        profile.vehicle_number = request.POST.get('vehicle_number', '').strip()
        profile.emergency_contact = request.POST.get('emergency_contact', '').strip()
        profile.availability_status = request.POST.get('availability_status', profile.availability_status)

        if 'photo' in request.FILES:
            profile.photo = request.FILES['photo']

        profile.save()
        messages.success(request, 'Your delivery profile has been updated successfully.')
        return redirect('delivery_profile')

    return render(request, 'delivery/profile.html', {'profile': profile})


@login_required(login_url='login')
def delivery_orders(request):
    """Show assigned orders, delivery history, and monthly delivery statistics for the logged-in delivery boy."""
    if request.user.role != 'delivery':
        messages.error(request, "Access Denied. Delivery staff only.")
        return redirect('login')

    all_orders = Order.objects.filter(delivery_boy=request.user).order_by('-order_date')

    pending_orders = all_orders.filter(status='assigned').order_by('order_date')
    active_orders = all_orders.filter(status__in=['picked_up', 'out_for_delivery']).order_by('-order_date')
    completed_orders = all_orders.filter(status='delivered').order_by('-order_date')
    cancelled_orders = all_orders.filter(status='cancelled').order_by('-order_date')
    order_history = all_orders.filter(status__in=['delivered', 'cancelled']).order_by('-order_date')[:20]

    current_month = timezone.now().month
    current_year = timezone.now().year
    monthly_orders = all_orders.filter(
        order_date__month=current_month,
        order_date__year=current_year,
    )

    monthly_stats = {
        'total_deliveries': monthly_orders.filter(status='delivered').count(),
        'cancelled': monthly_orders.filter(status='cancelled').count(),
        'pending': monthly_orders.filter(status='assigned').count(),
        'earnings_placeholder': f"Rs. {monthly_orders.filter(status='delivered').count() * 0}",
    }

    return render(request, 'delivery/orders.html', {
        'pending_orders': pending_orders,
        'active_orders': active_orders,
        'completed_orders': completed_orders,
        'cancelled_orders': cancelled_orders,
        'order_history': order_history,
        'monthly_stats': monthly_stats,
        'total_deliveries': all_orders.filter(status='delivered').count(),
    })


@login_required(login_url='login')
def accept_order(request, order_id):
    """
    Assigns an order to the delivery boy and marks it Out for Delivery.
    """
    if request.user.role != 'delivery':
        return redirect('login')

    order = get_object_or_404(Order, id=order_id, delivery_boy__isnull=True)
    assign_order_to_delivery_boy(order, request.user, status='assigned')

    # Log notification
    Notification.objects.create(
        user=order.student,
        title="Tiffin Out for Delivery!",
        message=f"Your tiffin from {order.mess.mess_name} has been picked up by {request.user.username} and is on its way.",
        notification_type='push'
    )

    messages.success(request, f"Order #{order.id} accepted. Deliver it to: {order.student.address}")
    return redirect('delivery_dashboard')


@login_required(login_url='login')
def update_delivery_status(request, order_id, target_status):
    """Advance a delivery boy's assigned order through the shared workflow."""
    if request.user.role != 'delivery':
        return redirect('login')

    order = get_object_or_404(Order, id=order_id, delivery_boy=request.user)
    if request.method != 'POST':
        return redirect('delivery_orders')

    allowed_targets = {
        'picked_up': 'assigned',
        'out_for_delivery': 'picked_up',
        'delivered': 'out_for_delivery',
    }

    if target_status not in allowed_targets:
        messages.error(request, 'Invalid delivery status update.')
        return redirect('delivery_orders')

    if order.status != allowed_targets[target_status]:
        messages.error(request, 'This order cannot be updated to that state yet.')
        return redirect('delivery_orders')

    if target_status == 'delivered':
        transition_order_status(order, target_status)
        set_delivery_boy_availability(request.user, True)
        messages.success(request, f'Order #{order.id} delivered successfully. You are now available for the next assignment.')
    else:
        transition_order_status(order, target_status)
        if target_status in {'picked_up', 'out_for_delivery'}:
            set_delivery_boy_availability(request.user, False)
        messages.success(request, f'Order #{order.id} moved to {dict(Order.STATUS_CHOICES)[target_status]}.')
    return redirect('delivery_orders')


@login_required(login_url='login')
def verify_delivery_otp(request, order_id):
    """
    Verifies the 6-digit OTP provided by the student to finalize delivery.
    """
    if request.user.role != 'delivery':
        return redirect('login')

    order = get_object_or_404(Order, id=order_id, delivery_boy=request.user)
    
    if request.method == "POST":
        input_otp = request.POST.get('otp')
        if order.delivery_otp == input_otp:
            transition_order_status(order, 'delivered')
            set_delivery_boy_availability(request.user, True)

            # Notify student
            Notification.objects.create(
                user=order.student,
                title="Tiffin Delivered!",
                message=f"Your order #{order.id} has been delivered successfully. Enjoy your meal!",
                notification_type='email'
            )
            
            messages.success(request, f"Delivery verified successfully for Order #{order.id}!")
        else:
            messages.error(request, "Incorrect OTP. Please ask the student for the correct code.")

    return redirect('delivery_dashboard')


@login_required(login_url='login')
def accept_delivery_assignment(request, order_id):
    """
    Delivery boy accepts the assigned order and it moves to 'out_for_delivery' status.
    """
    if request.user.role != 'delivery':
        return redirect('login')

    order = get_object_or_404(Order, id=order_id, delivery_boy=request.user, status='assigned')
    
    if request.method == "POST":
        transition_order_status(order, 'out_for_delivery')
        profile, _ = DeliveryBoyProfile.objects.get_or_create(user=request.user)
        profile.availability_status = 'busy'
        profile.save(update_fields=['availability_status'])

        Notification.objects.create(
            user=order.student,
            title="Tiffin Out for Delivery!",
            message=f"Your tiffin from {order.mess.mess_name} has been picked up by {request.user.first_name or request.user.username} and is on its way.",
            notification_type='push'
        )
        
        messages.success(request, f"Order #{order.id} accepted. You are now delivering it to: {order.student.address}")
    
    return redirect('delivery_dashboard')


@login_required(login_url='login')
def reject_delivery_assignment(request, order_id):
    """
    Delivery boy rejects the assigned order. The assignment is cleared and order goes back to 'preparing' status.
    """
    if request.user.role != 'delivery':
        return redirect('login')

    order = get_object_or_404(Order, id=order_id, delivery_boy=request.user, status='assigned')
    
    if request.method == "POST":
        order.delivery_boy = None
        order.save(update_fields=['delivery_boy'])
        try:
            transition_order_status(order, 'ready_for_pickup')
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('delivery_dashboard')

        Notification.objects.create(
            user=order.mess.vendor,
            title="Delivery Assignment Rejected",
            message=f"Delivery boy {request.user.first_name or request.user.username} has rejected Order #{order.id}. Please reassign it.",
            notification_type='push'
        )
        
        messages.success(request, f"Order #{order.id} rejected. It is now available for other delivery boys.")
    
    return redirect('delivery_dashboard')


@login_required(login_url='login')
def route_tracking(request, order_id):
    """
    Visual route mock showing directions between Mess and Student Hostel address.
    """
    if request.user.role != 'delivery':
        return redirect('login')

    order = get_object_or_404(Order, id=order_id, delivery_boy=request.user)
    return render(request, 'delivery/route_tracking.html', {'order': order})
