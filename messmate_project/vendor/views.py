from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count

from accounts.models import VendorProfile
from vendor.models import Mess, Meal
from student.models import Order, Subscription, Review, Complaint, Payment
from core.ai_services import forecast_demand, predict_food_waste


@login_required(login_url='login')
def vendor_dashboard(request):
    """
    Displays Vendor Dashboard with comprehensive financial analytics, AI demand forecasting,
    food waste predictions, and sentiment metrics.
    """
    if request.user.role != 'vendor':
        messages.error(request, "Access Denied. Vendors only.")
        return redirect('login')

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


@login_required(login_url='login')
def add_mess(request):
    if request.user.role != 'vendor':
        return redirect('login')

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
            distance=float(distance),
            monthly_price_lunch=float(monthly_price_lunch),
            monthly_price_dinner=float(monthly_price_dinner),
            monthly_price_both=float(monthly_price_both),
            daily_tiffin_price=float(daily_tiffin_price)
        )

        messages.success(request, "Mess created successfully!")
        return redirect('manage_mess')

    return render(request, 'vendor/add_mess.html')


@login_required(login_url='login')
def manage_mess(request):
    if request.user.role != 'vendor':
        return redirect('login')

    messes = Mess.objects.filter(vendor=request.user)
    return render(request, 'vendor/manage_mess.html', {'messes': messes})


@login_required(login_url='login')
def edit_mess(request, mess_id):
    mess = get_object_or_404(Mess, id=mess_id, vendor=request.user)
    if request.method == "POST":
        mess.mess_name = request.POST.get('mess_name')
        mess.address = request.POST.get('address')
        mess.contact_number = request.POST.get('contact_number')
        mess.description = request.POST.get('description')
        mess.diet_type = request.POST.get('diet_type')
        mess.location_name = request.POST.get('location_name')
        mess.distance = float(request.POST.get('distance', 1.0))
        mess.monthly_price_lunch = float(request.POST.get('monthly_price_lunch', 0))
        mess.monthly_price_dinner = float(request.POST.get('monthly_price_dinner', 0))
        mess.monthly_price_both = float(request.POST.get('monthly_price_both', 0))
        mess.daily_tiffin_price = float(request.POST.get('daily_tiffin_price', 0))
        mess.save()
        messages.success(request, "Mess updated successfully!")
        return redirect('manage_mess')
        
    return render(request, 'vendor/edit_mess.html', {'mess': mess})


@login_required(login_url='login')
def delete_mess(request, mess_id):
    mess = get_object_or_404(Mess, id=mess_id, vendor=request.user)
    mess.delete()
    messages.success(request, "Mess deleted successfully!")
    return redirect('manage_mess')


@login_required(login_url='login')
def manage_meals(request, mess_id):
    if request.user.role != 'vendor':
        return redirect('login')

    mess = get_object_or_404(Mess, id=mess_id, vendor=request.user)
    meals = Meal.objects.filter(mess=mess)
    return render(request, 'vendor/manage_meals.html', {'mess': mess, 'meals': meals})


@login_required(login_url='login')
def add_meal(request, mess_id):
    if request.user.role != 'vendor':
        return redirect('login')

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


@login_required(login_url='login')
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


@login_required(login_url='login')
def delete_meal(request, meal_id):
    meal = get_object_or_404(Meal, id=meal_id, mess__vendor=request.user)
    mess_id = meal.mess.id
    meal.delete()
    messages.success(request, "Meal deleted successfully!")
    return redirect('manage_meals', mess_id=mess_id)


@login_required(login_url='login')
def orders(request):
    if request.user.role != 'vendor':
        return redirect('login')

    messes = Mess.objects.filter(vendor=request.user)
    vendor_orders = Order.objects.filter(mess__in=messes).order_by('-order_date')
    return render(request, 'vendor/orders.html', {'orders': vendor_orders})


@login_required(login_url='login')
def update_order_status(request, order_id):
    order = get_object_or_404(Order, id=order_id, mess__vendor=request.user)
    if request.method == "POST":
        new_status = request.POST.get('status')
        order.status = new_status
        order.save()
        messages.success(request, f"Order #{order.id} status updated to {new_status.replace('_', ' ').title()}.")
    return redirect('vendor_orders')


@login_required(login_url='login')
def earnings(request):
    if request.user.role != 'vendor':
        return redirect('login')
        
    messes = Mess.objects.filter(vendor=request.user)
    # Summarize payments
    payments = Payment.objects.filter(order__mess__in=messes, status='success') | Payment.objects.filter(subscription__mess__in=messes, status='success')
    return render(request, 'vendor/earnings.html', {'payments': payments})


@login_required(login_url='login')
def profile(request):
    if request.user.role != 'vendor':
        return redirect('login')

    profile, _ = VendorProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        profile.business_name = request.POST.get('business_name')
        profile.business_address = request.POST.get('business_address')
        profile.contact_number = request.POST.get('contact_number')
        profile.gst_number = request.POST.get('gst_number')
        profile.fssai_license = request.POST.get('fssai_license')
        if 'documents' in request.FILES:
            profile.documents = request.FILES['documents']
        profile.save()
        
        request.user.first_name = request.POST.get('first_name', '')
        request.user.last_name = request.POST.get('last_name', '')
        request.user.save()

        messages.success(request, "Business profile details updated successfully! Wait for Admin verification.")
        return redirect('vendor_profile')

    return render(request, 'vendor/profile.html', {'profile': profile})


@login_required(login_url='login')
def respond_complaint(request, complaint_id):
    complaint = get_object_or_404(Complaint, id=complaint_id, mess__vendor=request.user)
    if request.method == "POST":
        response = request.POST.get('response')
        complaint.response = response
        complaint.status = 'resolved'
        complaint.save()
        messages.success(request, f"Complaint #{complaint.id} marked as RESOLVED with response.")
    return redirect('vendor_dashboard')


@login_required(login_url='login')
def subscriptions(request):
    if request.user.role != 'vendor':
        return redirect('login')
        
    messes = Mess.objects.filter(vendor=request.user)
    vendor_subscriptions = Subscription.objects.filter(mess__in=messes).order_by('-start_date')
    return render(request, 'vendor/subscriptions.html', {'subscriptions': vendor_subscriptions})