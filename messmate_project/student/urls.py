from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.student_dashboard, name='student_dashboard'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('wallet/', views.wallet_detail, name='wallet_detail'),
    path('mess/<int:mess_id>/', views.mess_detail, name='mess_detail'),
    path('subscribe/<int:mess_id>/', views.subscribe_plan, name='subscribe_plan'),
    path('subscription/pause/<int:sub_id>/', views.pause_subscription, name='pause_subscription'),
    path('subscription/resume/<int:sub_id>/', views.resume_subscription, name='resume_subscription'),
    path('subscription/cancel/<int:sub_id>/', views.cancel_subscription, name='cancel_subscription'),
    
    path('cart/', views.view_cart, name='view_cart'),
    path('cart/add/<int:meal_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/update/<int:item_id>/', views.update_cart, name='update_cart'),
    path('cart/checkout/', views.checkout_cart, name='checkout_cart'),
    path('order/track/<int:order_id>/', views.track_order, name='track_order'),
    
    path('review/add/<int:mess_id>/', views.add_review, name='add_review'),
    path('complaint/submit/', views.submit_complaint, name='submit_complaint'),
    path('invoice/download/<int:payment_id>/', views.download_invoice, name='download_invoice'),
]