from django.urls import path, include
from .views import *
from rest_framework.routers import DefaultRouter


router = DefaultRouter()
router.register(r'cart', CartViewSet, basename='cart')


urlpatterns = [
    path('products/', ItemListCreate.as_view(), name='item-list-create'),
    path('products/<int:pk>/', ProductDetailView.as_view(), name='product-detail'),
    path('', include(router.urls)),
]
