from django.urls import path
from . import views
from . import delivery_views
from . import admin_views

urlpatterns = [
    path('', views.home, name='home'),
    path('api/chatbot/', views.chatbot_api, name='chatbot_api'),
    path('api/recommend/', views.recommendation_api, name='recommendation_api'),
    
    # Delivery Boy paths
    path('delivery/dashboard/', delivery_views.delivery_dashboard, name='delivery_dashboard'),
    path('delivery/profile/', delivery_views.delivery_profile, name='delivery_profile'),
    path('delivery/orders/', delivery_views.delivery_orders, name='delivery_orders'),
    path('delivery/accept/<int:order_id>/', delivery_views.accept_order, name='accept_order'),
    path('delivery/accept-assignment/<int:order_id>/', delivery_views.accept_delivery_assignment, name='accept_delivery_assignment'),
    path('delivery/reject-assignment/<int:order_id>/', delivery_views.reject_delivery_assignment, name='reject_delivery_assignment'),
    path('delivery/update-status/<int:order_id>/<slug:target_status>/', delivery_views.update_delivery_status, name='update_delivery_status'),
    path('delivery/verify-otp/<int:order_id>/', delivery_views.verify_delivery_otp, name='verify_delivery_otp'),
    path('delivery/route/<int:order_id>/', delivery_views.route_tracking, name='route_tracking'),
    
    # Admin paths
    path('admin-dashboard/', admin_views.admin_dashboard, name='admin_dashboard'),
    path('admin-dashboard/vendor/<int:profile_id>/approve/', admin_views.approve_vendor, name='approve_vendor'),
    path('admin-dashboard/vendor/<int:profile_id>/reject/', admin_views.reject_vendor, name='reject_vendor'),
    path('admin-dashboard/vendor/<int:profile_id>/suspend/', admin_views.suspend_vendor, name='suspend_vendor'),
    path('admin-dashboard/complaint/<int:complaint_id>/respond/', admin_views.admin_respond_complaint, name='admin_respond_complaint'),
]
