from django.urls import path
from . import views

app_name = 'adminpanel'

urlpatterns = [
    path('', views.admin_dashboard, name='admin_dashboard'),
    path('students/', views.manage_students, name='manage_students'),
    path('students/<int:user_id>/toggle-status/', views.toggle_student_status, name='toggle_student_status'),
    path('students/<int:user_id>/profile/', views.student_profile, name='student_profile'),
    path('vendors/', views.manage_vendors, name='manage_vendors'),
    path('vendors/<int:user_id>/toggle-status/', views.toggle_vendor_status, name='toggle_vendor_status'),
    path('vendors/<int:user_id>/approve/', views.approve_vendor, name='approve_vendor'),
    path('vendors/<int:user_id>/reject/', views.reject_vendor, name='reject_vendor'),
    path('vendors/<int:user_id>/profile/', views.vendor_profile, name='vendor_profile'),
    path('messes/', views.manage_messes, name='manage_messes'),
    path('messes/<int:mess_id>/', views.mess_detail, name='mess_detail'),
    path('messes/<int:mess_id>/edit/', views.edit_mess, name='edit_mess'),
    path('messes/<int:mess_id>/toggle-status/', views.toggle_mess_status, name='toggle_mess_status'),
    path('messes/<int:mess_id>/approve/', views.approve_mess, name='approve_mess'),
    path('messes/<int:mess_id>/reject/', views.reject_mess, name='reject_mess'),
    path('messes/<int:mess_id>/delete/', views.delete_mess, name='delete_mess'),
    path('meals/', views.manage_meals, name='manage_meals'),
    path('meals/<int:meal_id>/', views.meal_detail, name='meal_detail'),
    path('meals/<int:meal_id>/edit/', views.edit_meal, name='edit_meal'),
    path('meals/<int:meal_id>/toggle-status/', views.toggle_meal_status, name='toggle_meal_status'),
    path('meals/<int:meal_id>/delete/', views.delete_meal, name='delete_meal'),
]
