import os

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, Sum, Count

from accounts.models import VendorProfile
from vendor.models import Mess, Meal
from student.models import Order, Subscription, Review, Complaint, Payment
from core.ai_services import forecast_demand, predict_food_waste
from core.decorators import vendor_required


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

    # Review Sentiment Metrics
    reviews = Review.objects.filter(mess__in=messes)
    sentiment_stats = reviews.values('sentiment').annotate(count=Count('id'))
    sentiment_dict = {'positive': 0, 'neutral': 0, 'negative': 0}
    for stat in sentiment_stats:
        sentiment_dict[stat['sentiment']] = stat['count']

    # Total complaints
    complaints = Complaint.objects.filter(mess__in=messes).order_by('-created_at')[:5]

    context = {
        'messes': messes,
        'active_subs_count': active_subs_count,
        'total_orders_count': total_orders_count,
        'total_revenue': total_revenue,
        'popular_meals': popular_meals,
        'forecast': forecast,
        'waste': waste,
        'sentiment': sentiment_dict,
        'complaints': complaints,
        'first_mess': first_mess
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
            distance=float(distance or 1.0),
            monthly_price_lunch=float(monthly_price_lunch or 0.00),
            monthly_price_dinner=float(monthly_price_dinner or 0.00),
            monthly_price_both=float(monthly_price_both or 0.00),
            daily_tiffin_price=float(daily_tiffin_price or 0.00)
        )

        messages.success(request, "Mess created successfully!")
        return redirect('manage_mess')

    return render(request, 'vendor/add_mess.html')


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
        mess.distance = float(request.POST.get('distance') or 1.0)
        mess.monthly_price_lunch = float(request.POST.get('monthly_price_lunch') or 0.0)
        mess.monthly_price_dinner = float(request.POST.get('monthly_price_dinner') or 0.0)
        mess.monthly_price_both = float(request.POST.get('monthly_price_both') or 0.0)
        mess.daily_tiffin_price = float(request.POST.get('daily_tiffin_price') or 0.0)
        mess.save()
        messages.success(request, "Mess updated successfully!")
        return redirect('manage_mess')
        
    return render(request, 'vendor/edit_mess.html', {'mess': mess})


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
    vendor_orders = Order.objects.filter(mess__in=messes).order_by('-order_date')
    return render(request, 'vendor/orders.html', {'orders': vendor_orders})


@vendor_required
def update_order_status(request, order_id):
    order = get_object_or_404(Order, id=order_id, mess__vendor=request.user)
    if request.method == "POST":
        new_status = request.POST.get('status')
        allowed_statuses = [choice[0] for choice in Order.STATUS_CHOICES]
        if new_status in allowed_statuses:
            order.status = new_status
            order.save()
            messages.success(request, f"Order #{order.id} status updated to {new_status.replace('_', ' ').title()}.")
        else:
            messages.error(request, "Invalid order status.")
    return redirect('vendor_orders')


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
        messages.success(request, f"Complaint #{complaint.id} marked as RESOLVED with response.")
    return redirect('vendor_dashboard')


@vendor_required
def subscriptions(request):
    messes = Mess.objects.filter(vendor=request.user)
    vendor_subscriptions = Subscription.objects.filter(mess__in=messes).order_by('-start_date')
    return render(request, 'vendor/subscriptions.html', {'subscriptions': vendor_subscriptions})

