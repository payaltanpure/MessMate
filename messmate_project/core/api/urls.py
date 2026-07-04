from django.urls import path, include
from rest_framework import routers
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from .views import (
    UserViewSet, MessViewSet, MealViewSet, 
    SubscriptionViewSet, OrderViewSet, ReviewViewSet, ComplaintViewSet
)

# Swagger Schema setup
schema_view = get_schema_view(
   openapi.Info(
      title="SMARTMESS AI API",
      default_version='v1',
      description="API documentation for SMARTMESS AI Hostel Mess and Tiffin Platform",
      contact=openapi.Contact(email="support@smartmess.ai"),
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
)

router = routers.DefaultRouter()
router.register('users', UserViewSet)
router.register('messes', MessViewSet)
router.register('meals', MealViewSet)
router.register('subscriptions', SubscriptionViewSet)
router.register('orders', OrderViewSet)
router.register('reviews', ReviewViewSet)
router.register('complaints', ComplaintViewSet)

urlpatterns = [
    # JWT authentication endpoints
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Base API routes
    path('', include(router.urls)),
    
    # Swagger & ReDoc Documentation paths
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]
