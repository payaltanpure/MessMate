from rest_framework import serializers
from accounts.models import User, StudentProfile, VendorProfile
from vendor.models import Mess, Meal
from student.models import Subscription, Order, OrderItem, Review, Complaint

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'phone', 'address', 'role', 'email_verified']


class StudentProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    class Meta:
        model = StudentProfile
        fields = ['id', 'user', 'photo', 'wallet_balance', 'cashback_balance']


class VendorProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    class Meta:
        model = VendorProfile
        fields = ['id', 'user', 'business_name', 'business_address', 'contact_number', 'verification_status', 'gst_number', 'fssai_license']


class MealSerializer(serializers.ModelSerializer):
    class Meta:
        model = Meal
        fields = ['id', 'mess', 'meal_type', 'name', 'menu_items', 'price', 'is_available']


class MessSerializer(serializers.ModelSerializer):
    meals = MealSerializer(many=True, read_only=True)
    class Meta:
        model = Mess
        fields = ['id', 'vendor', 'mess_name', 'address', 'contact_number', 'description', 'diet_type', 'location_name', 'distance', 'average_rating', 'is_active', 'meals']


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = ['id', 'student', 'mess', 'plan_type', 'start_date', 'end_date', 'price_paid', 'status', 'remaining_days', 'consumed_meals', 'missed_meals']


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['id', 'meal', 'quantity', 'price']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    class Meta:
        model = Order
        fields = ['id', 'student', 'mess', 'order_date', 'total_amount', 'status', 'delivery_boy', 'delivery_otp', 'items']


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ['id', 'student', 'mess', 'rating', 'comment', 'photo', 'sentiment', 'created_at']


class ComplaintSerializer(serializers.ModelSerializer):
    class Meta:
        model = Complaint
        fields = ['id', 'student', 'mess', 'order', 'category', 'description', 'status', 'response', 'created_at']
