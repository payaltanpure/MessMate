from django.urls import path
from . import views

urlpatterns = [
    path('create/', views.create_payment, name='create_payment'),
    path('verify/', views.verify_payment, name='verify_payment'),
    path('cancel/', views.cancel_payment, name='cancel_payment'),
    path('fail/', views.fail_payment, name='fail_payment'),
    path('history/', views.payment_history, name='payment_history'),
    path('wallet/recharge/', views.wallet_recharge, name='wallet_recharge'),
    path('transactions/', views.transaction_history, name='transaction_history'),
    path('page/<uuid:payment_id>/', views.payment_page, name='payment_page'),
    path('process/<uuid:payment_id>/', views.process_payment, name='process_payment'),
    path('success/<uuid:payment_id>/', views.payment_success, name='payment_success'),
    path('failed/<uuid:payment_id>/', views.payment_failed, name='payment_failed'),
]
