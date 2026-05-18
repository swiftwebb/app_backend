from django.shortcuts import render

# Create your views here.
from rest_framework import generics
from .models import *
from .serializers import *

class ItemListCreate(generics.ListCreateAPIView):
    queryset = Product.objects.all()
    serializer_class = ItemSerializer



class ProductDetailView(generics.RetrieveAPIView):
    queryset = Product.objects.all().prefetch_related('variations')
    serializer_class = ProductDetailSerializer



