from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from student.models import Order, Notification
from accounts.models import DeliveryBoyProfile

@login_required(login_url='login')
def delivery_dashboard(request):
    """
    Dashboard for delivery staff showing assigned orders, pickup pool, and delivery verification.
    """
    if request.user.role != 'delivery':
        messages.error(request, "Access Denied. Delivery staff only.")
        return redirect('login')

    # Get delivery boy profile
    db_profile, _ = DeliveryBoyProfile.objects.get_or_create(user=request.user)

    # Active deliveries assigned to this delivery boy
    my_deliveries = Order.objects.filter(
        delivery_boy=request.user, 
        status__in=['accepted', 'preparing', 'out_for_delivery']
    ).order_by('-order_date')

    # Pickup pool (orders that are ready/preparing but not yet picked up by anyone)
    pickup_pool = Order.objects.filter(
        delivery_boy__isnull=True, 
        status__in=['accepted', 'preparing']
    ).order_by('order_date')

    # Completed history
    completed_deliveries = Order.objects.filter(
        delivery_boy=request.user, 
        status='delivered'
    ).order_by('-order_date')[:10]

    context = {
        'profile': db_profile,
        'my_deliveries': my_deliveries,
        'pickup_pool': pickup_pool,
        'completed_deliveries': completed_deliveries,
    }
    return render(request, 'delivery/dashboard.html', context)


@login_required(login_url='login')
def accept_order(request, order_id):
    """
    Assigns an order to the delivery boy and marks it Out for Delivery.
    """
    if request.user.role != 'delivery':
        return redirect('login')

    order = get_object_or_404(Order, id=order_id, delivery_boy__isnull=True)
    order.delivery_boy = request.user
    order.status = 'out_for_delivery'
    order.save()

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
            order.status = 'delivered'
            order.save()

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
def route_tracking(request, order_id):
    """
    Visual route mock showing directions between Mess and Student Hostel address.
    """
    if request.user.role != 'delivery':
        return redirect('login')

    order = get_object_or_404(Order, id=order_id, delivery_boy=request.user)
    return render(request, 'delivery/route_tracking.html', {'order': order})
