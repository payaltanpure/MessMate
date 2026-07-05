from django.contrib import admin
from .models import Payment, Subscription, WalletTransaction


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'payment_id', 'user', 'amount', 'status', 'payment_method', 'payment_gateway', 'created_at')
    list_filter = ('status', 'payment_method', 'payment_gateway')
    search_fields = ('payment_id', 'gateway_transaction_id', 'user__username')
    readonly_fields = ('payment_id', 'created_at', 'updated_at')


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'transaction_type', 'amount', 'created_at')
    list_filter = ('transaction_type',)
    search_fields = ('user__username', 'description')


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'student', 'mess', 'plan_type', 'status', 'start_date', 'end_date')
    list_filter = ('plan_type', 'status')
    search_fields = ('student__username', 'mess__mess_name')
