from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.vendor_dashboard, name='vendor_dashboard'),
    path('add-mess/', views.add_mess, name='add_mess'), 
    path('manage-mess/', views.manage_mess, name='manage_mess'),
    path('mess/edit/<int:mess_id>/', views.edit_mess, name='edit_mess'),
    path('mess/delete/<int:mess_id>/', views.delete_mess, name='delete_mess'),
    
    path('mess/<int:mess_id>/meals/', views.manage_meals, name='manage_meals'),
    path('mess/<int:mess_id>/add-meal/', views.add_meal, name='add_meal'),
    path('meal/edit/<int:meal_id>/', views.edit_meal, name='edit_meal'),
    path('meal/delete/<int:meal_id>/', views.delete_meal, name='delete_meal'),
    
    path('orders/', views.orders, name='vendor_orders'),
    path('order/update-status/<int:order_id>/', views.update_order_status, name='update_order_status'),
    
    path('earnings/', views.earnings, name='vendor_earnings'),
    path('profile/', views.profile, name='vendor_profile'),
    
    path('complaint/respond/<int:complaint_id>/', views.respond_complaint, name='respond_complaint'),
]
