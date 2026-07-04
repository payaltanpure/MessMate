from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action

from accounts.models import User
from vendor.models import Mess, Meal
from student.models import Subscription, Order, Review, Complaint
from .serializers import (
    UserSerializer, MessSerializer, MealSerializer, 
    SubscriptionSerializer, OrderSerializer, ReviewSerializer, ComplaintSerializer
)

class IsOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.vendor == request.user or request.user.is_superuser


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAdminUser]


class MessViewSet(viewsets.ModelViewSet):
    queryset = Mess.objects.filter(is_active=True)
    serializer_class = MessSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        # Allow vendors to see their own messes even if inactive
        user = self.request.user
        if user.is_authenticated and user.role == 'vendor':
            return Mess.objects.filter(vendor=user)
        return Mess.objects.filter(is_active=True)


class MealViewSet(viewsets.ModelViewSet):
    queryset = Meal.objects.all()
    serializer_class = MealSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class SubscriptionViewSet(viewsets.ModelViewSet):
    queryset = Subscription.objects.all()
    serializer_class = SubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'student':
            return Subscription.objects.filter(student=user)
        elif user.role == 'vendor':
            return Subscription.objects.filter(mess__vendor=user)
        return Subscription.objects.all()


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'student':
            return Order.objects.filter(student=user)
        elif user.role == 'vendor':
            return Order.objects.filter(mess__vendor=user)
        elif user.role == 'delivery':
            return Order.objects.filter(delivery_boy=user)
        return Order.objects.all()

    @action(detail=True, methods=['post'], url_path='verify-otp')
    def verify_otp(self, request, pk=None):
        order = self.get_object()
        otp = request.data.get('otp')
        if order.delivery_otp == otp:
            order.status = 'delivered'
            order.save()
            return Response({'status': 'Delivery verified. Status updated to Delivered.'}, status=status.HTTP_200_OK)
        return Response({'error': 'Incorrect OTP.'}, status=status.HTTP_400_BAD_REQUEST)


class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class ComplaintViewSet(viewsets.ModelViewSet):
    queryset = Complaint.objects.all()
    serializer_class = ComplaintSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'student':
            return Complaint.objects.filter(student=user)
        elif user.role == 'vendor':
            return Complaint.objects.filter(mess__vendor=user)
        return Complaint.objects.all()
