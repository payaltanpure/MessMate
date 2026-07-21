import os

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, Sum, Count
from django.conf import settings

from accounts.models import VendorProfile, DeliveryBoyProfile, User
from vendor.models import Mess, Meal
from student.models import Order, Subscription, Review, Complaint, Payment
from core.ai_services import forecast_demand, predict_food_waste, get_ai_insights, get_recommended_meals
from core.maps_service import get_maps_config, get_mess_map_data
from core.decorators import vendor_required
from core.email_services import send_vendor_notification
from core.weather_service import get_weather, get_weather_impact
from core.delivery_views import assign_order_to_delivery_boy, can_reassign_delivery, set_delivery_boy_availability, transition_order_status


@vendor_required
def vendor_dashboard(request):
    """
    Displays Vendor Dashboard with comprehensive financial analytics, AI demand forecasting,
    food waste predictions, and sentiment metrics.
    """

    messes = Mess.objects.filter(vendor=request.user)
    first_mess = messes.first()

    # Base counts
    active_subs_count = Subscription.objects.filter(mess__in=messes, status='active').count()
    total_orders_count = Order.objects.filter(mess__in=messes).count()
    pending_orders_count = Order.objects.filter(mess__in=messes, status='pending').count()
    preparing_orders_count = Order.objects.filter(mess__in=messes, status='preparing').count()
    ready_for_pickup_count = Order.objects.filter(mess__in=messes, status='ready_for_pickup').count()
    assigned_orders_count = Order.objects.filter(mess__in=messes, status='assigned').count()
    delivered_orders_count = Order.objects.filter(mess__in=messes, status__in=['delivered', 'completed']).count()
    cancelled_orders_count = Order.objects.filter(mess__in=messes, status='cancelled').count()

    # Revenue calculations from payments (both orders and subscriptions)
    order_rev = Payment.objects.filter(order__mess__in=messes, status='success').aggregate(Sum('amount'))['amount__sum'] or 0.00
    sub_rev = Payment.objects.filter(subscription__mess__in=messes, status='success').aggregate(Sum('amount'))['amount__sum'] or 0.00
    total_revenue = float(order_rev) + float(sub_rev)

    # Popular meals
    popular_meals = Meal.objects.filter(mess__in=messes).annotate(
        order_count=Count('orderitem')
    ).order_by('-order_count')[:5]

    # AI forecasting & food waste
    forecast = {'tomorrow': 0, 'weekly': 0, 'monthly': 0}
    waste = {'expected_diners': 0, 'cooked_meals_estimate': 0, 'excess': 0, 'shortage': 0, 'recommendation': "No data available."}
    
    if first_mess:
        forecast = forecast_demand(first_mess.id)
        waste = predict_food_waste(first_mess.id)

    # Recommendation insights
    all_vendor_meals = Meal.objects.filter(mess__in=messes).select_related('mess')
    recommendation_stats = []
    meal_recommendation_counts = {}

    for meal in all_vendor_meals:
        meal_recommendation_counts[meal.id] = 0

    for user in request.user.__class__.objects.filter(role='student'):
        try:
            for meal in get_recommended_meals(user):
                if meal.id in meal_recommendation_counts:
                    meal_recommendation_counts[meal.id] += 1
        except Exception:
            continue

    recommendation_meals = []
    for meal in all_vendor_meals:
        recommendation_meals.append({
            'meal': meal,
            'score': meal_recommendation_counts.get(meal.id, 0),
        })

    recommendation_meals.sort(key=lambda item: item['score'], reverse=True)
    most_recommended = recommendation_meals[:3]
    least_recommended = list(reversed(recommendation_meals[-3:])) if len(recommendation_meals) >= 3 else recommendation_meals[:3]
    recommendation_stats = {
        'total_meals': len(recommendation_meals),
        'top_score': most_recommended[0]['score'] if most_recommended else 0,
        'lowest_score': least_recommended[-1]['score'] if least_recommended else 0,
        'avg_score': round(sum(item['score'] for item in recommendation_meals) / len(recommendation_meals), 2) if recommendation_meals else 0,
    }

    # Review Sentiment Metrics
    reviews = Review.objects.filter(mess__in=messes)
    sentiment_stats = reviews.values('sentiment').annotate(count=Count('id'))
    sentiment_dict = {'positive': 0, 'neutral': 0, 'negative': 0}
    for stat in sentiment_stats:
        sentiment_dict[stat['sentiment']] = stat['count']

    # Total complaints
    complaints = Complaint.objects.filter(mess__in=messes).order_by('-created_at')[:5]
    weather = get_weather('Bengaluru')
    weather_impact = get_weather_impact('Bengaluru')
    insights = get_ai_insights('vendor', request.user)

    context = {
        'messes': messes,
        'active_subs_count': active_subs_count,
        'total_orders_count': total_orders_count,
        'pending_orders_count': pending_orders_count,
        'preparing_orders_count': preparing_orders_count,
        'ready_for_pickup_count': ready_for_pickup_count,
        'assigned_orders_count': assigned_orders_count,
        'delivered_orders_count': delivered_orders_count,
        'cancelled_orders_count': cancelled_orders_count,
        'total_revenue': total_revenue,
        'popular_meals': popular_meals,
        'forecast': forecast,
        'waste': waste,
        'most_recommended': most_recommended,
        'least_recommended': least_recommended,
        'recommendation_stats': recommendation_stats,
        'sentiment': sentiment_dict,
        'complaints': complaints,
        'first_mess': first_mess,
        'weather': weather,
        'weather_impact': weather_impact,
        'insights': insights,
    }
    return render(request, 'vendor/dashboard.html', context)


@vendor_required
def add_mess(request):
    if request.method == "POST":
        mess_name = request.POST.get('mess_name')
        address = request.POST.get('address')
        contact_number = request.POST.get('contact_number')
        description = request.POST.get('description')
        diet_type = request.POST.get('diet_type')
        location_name = request.POST.get('location_name')
        latitude = request.POST.get('latitude') or None
        longitude = request.POST.get('longitude') or None
        distance = request.POST.get('distance', 1.0)
        
        monthly_price_lunch = request.POST.get('monthly_price_lunch', 0.00)
        monthly_price_dinner = request.POST.get('monthly_price_dinner', 0.00)
        monthly_price_both = request.POST.get('monthly_price_both', 0.00)
        daily_tiffin_price = request.POST.get('daily_tiffin_price', 0.00)

        if Mess.objects.filter(vendor=request.user, mess_name=mess_name).exists():
            messages.error(request, "You already created a mess with this name!")
            return redirect('add_mess')

        Mess.objects.create(
            vendor=request.user,
            mess_name=mess_name,
            address=address,
            contact_number=contact_number,
            description=description,
            diet_type=diet_type,
            location_name=location_name,
            latitude=float(latitude) if latitude not in [None, ''] else None,
            longitude=float(longitude) if longitude not in [None, ''] else None,
            distance=float(distance or 1.0),
            monthly_price_lunch=float(monthly_price_lunch or 0.00),
            monthly_price_dinner=float(monthly_price_dinner or 0.00),
            monthly_price_both=float(monthly_price_both or 0.00),
            daily_tiffin_price=float(daily_tiffin_price or 0.00)
        )

        messages.success(request, "Mess created successfully!")
        return redirect('manage_mess')

    return render(request, 'vendor/add_mess.html', {'google_maps_api_key': get_maps_config()['api_key'], 'maps_config': get_maps_config()})


@vendor_required
def manage_mess(request):
    messes = Mess.objects.filter(vendor=request.user)
    return render(request, 'vendor/manage_mess.html', {'messes': messes})


@vendor_required
def edit_mess(request, mess_id):
    mess = get_object_or_404(Mess, id=mess_id, vendor=request.user)
    if request.method == "POST":
        mess.mess_name = request.POST.get('mess_name')
        mess.address = request.POST.get('address')
        mess.contact_number = request.POST.get('contact_number')
        mess.description = request.POST.get('description')
        mess.diet_type = request.POST.get('diet_type')
        mess.location_name = request.POST.get('location_name')
        mess.latitude = float(request.POST.get('latitude')) if request.POST.get('latitude') not in [None, ''] else None
        mess.longitude = float(request.POST.get('longitude')) if request.POST.get('longitude') not in [None, ''] else None
        mess.distance = float(request.POST.get('distance') or 1.0)
        mess.monthly_price_lunch = float(request.POST.get('monthly_price_lunch') or 0.0)
        mess.monthly_price_dinner = float(request.POST.get('monthly_price_dinner') or 0.0)
        mess.monthly_price_both = float(request.POST.get('monthly_price_both') or 0.0)
        mess.daily_tiffin_price = float(request.POST.get('daily_tiffin_price') or 0.0)
        mess.save()
        messages.success(request, "Mess updated successfully!")
        return redirect('manage_mess')
        
    return render(request, 'vendor/edit_mess.html', {
        'mess': mess,
        'google_maps_api_key': get_maps_config()['api_key'],
        'maps_config': get_maps_config(),
        'mess_map_data': get_mess_map_data(mess),
    })


@vendor_required
def delete_mess(request, mess_id):
    if request.method != 'POST':
        messages.error(request, 'Invalid delete request.')
        return redirect('manage_mess')

    mess = get_object_or_404(Mess, id=mess_id, vendor=request.user)
    mess.delete()
    messages.success(request, "Mess deleted successfully!")
    return redirect('manage_mess')


@vendor_required
def manage_meals(request, mess_id):
    mess = get_object_or_404(Mess, id=mess_id, vendor=request.user)
    meals = Meal.objects.filter(mess=mess)
    return render(request, 'vendor/manage_meals.html', {'mess': mess, 'meals': meals})


@vendor_required
def add_meal(request, mess_id):
    mess = get_object_or_404(Mess, id=mess_id, vendor=request.user)

    if request.method == "POST":
        meal_type = request.POST.get('meal_type')
        name = request.POST.get('name')
        menu_items = request.POST.get('menu_items')
        price = request.POST.get('price')

        Meal.objects.create(
            mess=mess,
            meal_type=meal_type,
            name=name,
            menu_items=menu_items,
            price=price
        )

        messages.success(request, "Meal added successfully!")
        return redirect('manage_meals', mess_id=mess.id)

    return render(request, 'vendor/add_meal.html', {'mess': mess})


@vendor_required
def edit_meal(request, meal_id):
    meal = get_object_or_404(Meal, id=meal_id, mess__vendor=request.user)
    if request.method == "POST":
        meal.meal_type = request.POST.get('meal_type')
        meal.name = request.POST.get('name')
        meal.menu_items = request.POST.get('menu_items')
        meal.price = float(request.POST.get('price'))
        meal.is_available = 'is_available' in request.POST
        meal.save()
        messages.success(request, "Meal updated successfully!")
        return redirect('manage_meals', mess_id=meal.mess.id)
        
    return render(request, 'vendor/edit_meal.html', {'meal': meal})


@vendor_required
def delete_meal(request, meal_id):
    meal = get_object_or_404(Meal, id=meal_id, mess__vendor=request.user)
    if request.method != 'POST':
        messages.error(request, 'Invalid delete request.')
        return redirect('manage_meals', mess_id=meal.mess.id)

    mess_id = meal.mess.id
    meal.delete()
    messages.success(request, "Meal deleted successfully!")
    return redirect('manage_meals', mess_id=mess_id)


@vendor_required
def orders(request):
    messes = Mess.objects.filter(vendor=request.user)
    vendor_orders = (
        Order.objects.filter(mess__in=messes)
        .select_related('student', 'mess')
        .prefetch_related('items__meal')
        .order_by('-order_date')
    )
    return render(request, 'vendor/orders.html', {'orders': vendor_orders})


@vendor_required
def update_order_status(request, order_id):
    order = get_object_or_404(Order, id=order_id, mess__vendor=request.user)
    if request.method == "POST":
        new_status = request.POST.get('status')
        allowed_statuses = [choice[0] for choice in Order.STATUS_CHOICES]
        if new_status in allowed_statuses:
            try:
                transition_order_status(order, new_status)
                messages.success(request, f"Order #{order.id} status updated to {new_status.replace('_', ' ').title()}.")
            except ValueError as exc:
                messages.error(str(exc))
        else:
            messages.error(request, "Invalid order status.")
    return redirect('vendor_orders')


@vendor_required
def assign_delivery_boy(request, order_id):
    """Assign an active delivery boy to an order when it is ready for pickup."""
    order = get_object_or_404(Order, id=order_id, mess__vendor=request.user)

    if order.status not in ['ready_for_pickup', 'assigned']:
        messages.error(request, 'Delivery boys can only be assigned once the order is ready for pickup.')
        return redirect('vendor_orders')

    if not can_reassign_delivery(order):
        messages.error(request, 'Delivery assignment can only be changed before the delivery boy picks up the order.')
        return redirect('vendor_orders')

    if request.method == 'POST':
        delivery_boy_id = request.POST.get('delivery_boy')

        if not delivery_boy_id:
            messages.error(request, 'Please select a Delivery Boy.')
            return redirect('vendor_orders')

        try:
            delivery_boy = User.objects.get(
                id=delivery_boy_id,
                role='delivery',
                is_active=True,
            )
        except User.DoesNotExist:
            messages.error(request, 'Only active delivery boys can be assigned.')
            return redirect('vendor_orders')

        DeliveryBoyProfile.objects.get_or_create(
            user=delivery_boy,
            defaults={'availability_status': 'available'}
        )

        if order.delivery_boy_id == delivery_boy.id and order.status == 'assigned':
            messages.info(request, 'This delivery boy is already assigned to the order.')
            return redirect('vendor_orders')

        assign_order_to_delivery_boy(order, delivery_boy, status='assigned')
        messages.success(request, f'Delivery Boy {delivery_boy.first_name or delivery_boy.username} assigned to Order #{order.id}.')
        return redirect('vendor_orders')

    active_delivery_boys = User.objects.filter(
        role='delivery',
        is_active=True,
    ).select_related('delivery_profile').order_by('username')

    for delivery_boy in active_delivery_boys:
        DeliveryBoyProfile.objects.get_or_create(
            user=delivery_boy,
            defaults={'availability_status': 'available'}
        )

    context = {
        'order': order,
        'delivery_boys': active_delivery_boys,
    }
    return render(request, 'vendor/assign_delivery_boy.html', context)


@vendor_required
def earnings(request):
    messes = Mess.objects.filter(vendor=request.user)
    payments = Payment.objects.filter(
        Q(status='success') & (Q(order__mess__in=messes) | Q(subscription__mess__in=messes))
    ).order_by('-created_at')
    return render(request, 'vendor/earnings.html', {'payments': payments})


@vendor_required
def profile(request):
    profile, _ = VendorProfile.objects.get_or_create(
        user=request.user,
        defaults={
            'business_name': '',
            'business_address': '',
            'contact_number': '',
        }
    )
    if request.method == "POST":
        profile.business_name = request.POST.get('business_name')
        profile.business_address = request.POST.get('business_address')
        profile.contact_number = request.POST.get('contact_number')
        profile.gst_number = request.POST.get('gst_number')
        profile.fssai_license = request.POST.get('fssai_license')
        if 'documents' in request.FILES:
            uploaded_file = request.FILES['documents']
            allowed_extensions = ['.pdf', '.png', '.jpg', '.jpeg', '.gif']
            max_size = 5 * 1024 * 1024
            extension = os.path.splitext(uploaded_file.name)[1].lower()
            if extension not in allowed_extensions or uploaded_file.size > max_size:
                messages.error(request, "Invalid document upload. Please upload PDF/JPG/PNG/GIF under 5MB.")
                return redirect('vendor_profile')
            profile.documents = uploaded_file
        profile.save()
        
        request.user.first_name = request.POST.get('first_name', '')
        request.user.last_name = request.POST.get('last_name', '')
        request.user.save()

        messages.success(request, "Business profile details updated successfully! Wait for Admin verification.")
        return redirect('vendor_profile')

    return render(request, 'vendor/profile.html', {'profile': profile})


@vendor_required
def respond_complaint(request, complaint_id):
    complaint = get_object_or_404(Complaint, id=complaint_id, mess__vendor=request.user)
    if request.method == "POST":
        response = request.POST.get('response')
        complaint.response = response
        complaint.status = 'resolved'
        complaint.save()
        if complaint.student and complaint.student.email:
            send_vendor_notification(
                complaint.student.username,
                complaint.student.email,
                f'Complaint #{complaint.id} update',
                f'Your complaint has been responded to by the vendor.\nResponse: {response}',
                category='vendor_complaint',
            )
        messages.success(request, f"Complaint #{complaint.id} marked as RESOLVED with response.")
    return redirect('vendor_dashboard')


@vendor_required
def subscriptions(request):
    messes = Mess.objects.filter(vendor=request.user)
    vendor_subscriptions = Subscription.objects.filter(mess__in=messes).order_by('-start_date')
    return render(request, 'vendor/subscriptions.html', {'subscriptions': vendor_subscriptions})

