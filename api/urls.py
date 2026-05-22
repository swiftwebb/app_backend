from django.urls import path, include
from .views import *
from rest_framework.routers import DefaultRouter
from django.http import HttpResponse, HttpResponseRedirect
# Also add these Paystack URLs:
from django.http import HttpResponse, HttpResponseRedirect

router = DefaultRouter()
router.register(r'cart', CartViewSet, basename='cart')


urlpatterns = [
    path('products/', ItemListCreate.as_view(), name='item-list-create'),
    path('products/<int:pk>/', ProductDetailView.as_view(), name='product-detail'),
    path('', include(router.urls)),
    path('register/', RegisterAPIView.as_view(), name='api_register'),
    path('login/', LoginAPIView.as_view(), name='api_login'),
    
    path('logout/', LogoutAPIView.as_view(), name='api_logout'),

    # Add these two lines to your urlpatterns in urls.py

path('checkout/', CheckoutAPIView.as_view(), name='checkout'),
path('orders/', OrderListAPIView.as_view(), name='order-list'),

path('payment-success/',   PaymentSuccessView.as_view(),   name='payment-success'),
path('payment-cancelled/', PaymentCancelledView.as_view(), name='payment-cancelled'),


path('paystack/initialize/', InitializePaymentAPIView.as_view(), name='paystack-init'),
path('paystack/callback/',   PaystackCallbackAPIView.as_view(),  name='paystack-callback'),
path('paystack/webhook/',    PaystackWebhookAPIView.as_view(),   name='paystack-webhook'),
path('orders/<int:order_id>/verify/', VerifyPaymentAPIView.as_view(), name='verify-payment'),

]
