from django.shortcuts import render

# Create your views here.
from rest_framework import generics
from .models import *
from .serializers import *


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

class ItemListCreate(generics.ListCreateAPIView):
    queryset = Product.objects.all()
    serializer_class = ItemSerializer



class ProductDetailView(generics.RetrieveAPIView):
    queryset = Product.objects.all().prefetch_related('variations')
    serializer_class = ProductDetailSerializer



class LogoutAPIView(APIView):
    # This forces Django to require the mobile token to process this view
    permission_classes = [IsAuthenticated] 

    def post(self, request):
        try:
            # Delete the token from the database so it can never be used again
            request.user.auth_token.delete()
            return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
