from django.db import models
from django.conf import settings
from vendor.models import Mess, Meal
import uuid

class Subscription(models.Model):
    PLAN_CHOICES = (
        ('lunch', 'Lunch Only'),
        ('dinner', 'Dinner Only'),
        ('both', 'Lunch + Dinner'),
    )
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    )
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscriptions')
    mess = models.ForeignKey(Mess, on_delete=models.CASCADE, related_name='subscriptions')
    plan_type = models.CharField(max_length=10, choices=PLAN_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField()
    price_paid = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='active')
    remaining_days = models.IntegerField(default=30)
    consumed_meals = models.IntegerField(default=0)
    missed_meals = models.IntegerField(default=0)
    pause_date = models.DateField(null=True, blank=True)
    pause_remaining_days = models.IntegerField(default=30)

    def __str__(self):
        return f"{self.student.username} - {self.mess.mess_name} ({self.get_plan_type_display()})"


class Order(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('preparing', 'Preparing'),
        ('out_for_delivery', 'Out For Delivery'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    )
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='orders')
    mess = models.ForeignKey(Mess, on_delete=models.CASCADE, related_name='orders')
    order_date = models.DateTimeField(auto_now_add=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    delivery_boy = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL, 
        related_name='assigned_deliveries'
    )
    delivery_otp = models.CharField(max_length=6, blank=True, null=True)

    def __str__(self):
        return f"Order #{self.id} by {self.student.username} - {self.get_status_display()}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    meal = models.ForeignKey(Meal, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    price = models.DecimalField(max_digits=8, decimal_places=2)

    def __str__(self):
        return f"{self.quantity}x {self.meal.name} for Order #{self.order.id}"


class Cart(models.Model):
    student = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cart')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Cart of {self.student.username}"

    @property
    def total_price(self):
        return sum(item.total_price for item in self.items.all())


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    meal = models.ForeignKey(Meal, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)

    def __str__(self):
        return f"{self.quantity}x {self.meal.name} in cart"

    @property
    def total_price(self):
        return self.meal.price * self.quantity


class WalletTransaction(models.Model):
    TX_TYPE_CHOICES = (
        ('credit', 'Add Money'),
        ('debit', 'Payment/Debit'),
        ('cashback', 'Cashback Credit'),
        ('recharge', 'Recharge'),
        ('order_payment', 'Order Payment'),
        ('subscription_payment', 'Subscription Payment'),
        ('withdrawal', 'Withdrawal'),
        ('refund', 'Refund'),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wallet_transactions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=25, choices=TX_TYPE_CHOICES)
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_transaction_type_display()} - Rs.{self.amount}"


class Payment(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    )
    # New unified payment model fields
    payment_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.SET_NULL, related_name='payments')
    subscription = models.ForeignKey(Subscription, null=True, blank=True, on_delete=models.SET_NULL, related_name='payments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=30, default='online')
    payment_gateway = models.CharField(max_length=50, blank=True, null=True)
    gateway_transaction_id = models.CharField(max_length=200, blank=True, null=True, unique=True)
    # Backward-compatible raw razorpay fields (optional)
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=200, blank=True, null=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment #{self.id} - {self.user.username} - Rs.{self.amount} ({self.get_status_display()})"


class Review(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews')
    mess = models.ForeignKey(Mess, on_delete=models.CASCADE, related_name='reviews')
    rating = models.IntegerField(default=5) # 1 to 5 stars
    comment = models.TextField()
    photo = models.ImageField(upload_to='reviews/', blank=True, null=True)
    sentiment = models.CharField(max_length=10, default='neutral') # positive, negative, neutral
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Review ({self.rating}*) by {self.student.username} for {self.mess.mess_name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.mess.update_rating()


class Complaint(models.Model):
    CATEGORY_CHOICES = (
        ('food_quality', 'Food Quality Issue'),
        ('late_delivery', 'Late Delivery'),
        ('wrong_order', 'Wrong Order'),
        ('payment_issue', 'Payment Issue'),
    )
    STATUS_CHOICES = (
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
    )
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='complaints')
    mess = models.ForeignKey(Mess, on_delete=models.SET_NULL, null=True, blank=True, related_name='complaints')
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name='complaints')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    description = models.TextField()
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='open')
    response = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Complaint #{self.id} ({self.get_category_display()}) - {self.get_status_display()}"


class Notification(models.Model):
    TYPE_CHOICES = (
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('whatsapp', 'WhatsApp'),
        ('push', 'Push Notification'),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=150)
    message = models.TextField()
    notification_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    sent_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default='sent')

    def __str__(self):
        return f"Notification for {self.user.username}: {self.title}"
