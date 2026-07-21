from django.urls import path, include
from rest_framework import routers
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from .views import (
    UserViewSet, MessViewSet, MealViewSet, 
    SubscriptionViewSet, OrderViewSet, ReviewViewSet, ComplaintViewSet
)

class TokenObtainPairViewDocs(TokenObtainPairView):
    @swagger_auto_schema(
        tags=['Authentication'],
        operation_description='Authenticate a user and obtain JWT access and refresh tokens.',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['username', 'password'],
            properties={
                'username': openapi.Schema(type=openapi.TYPE_STRING, description='Username'),
                'password': openapi.Schema(type=openapi.TYPE_STRING, description='Password', format='password'),
            },
        ),
        responses={200: openapi.Response('Successful authentication', schema=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'access': openapi.Schema(type=openapi.TYPE_STRING, description='JWT access token'),
                'refresh': openapi.Schema(type=openapi.TYPE_STRING, description='JWT refresh token'),
            },
        ))},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class TokenRefreshViewDocs(TokenRefreshView):
    @swagger_auto_schema(
        tags=['Authentication'],
        operation_description='Refresh an expired access token using a valid refresh token.',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['refresh'],
            properties={
                'refresh': openapi.Schema(type=openapi.TYPE_STRING, description='Refresh token'),
            },
        ),
        responses={200: openapi.Response('New access token', schema=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'access': openapi.Schema(type=openapi.TYPE_STRING, description='JWT access token'),
            },
        ))},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


# Swagger Schema setup
schema_view = get_schema_view(
   openapi.Info(
      title="SMARTMESS AI API",
      default_version='v1',
      description="API documentation for SMARTMESS AI Hostel Mess and Tiffin Platform. Covers authentication, student, vendor, admin, and AI endpoints.",
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
    path('token/', TokenObtainPairViewDocs.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshViewDocs.as_view(), name='token_refresh'),
    
    # Base API routes
    path('', include(router.urls)),
    
    # Swagger & ReDoc Documentation paths
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]
