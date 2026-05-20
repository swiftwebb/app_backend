from django.shortcuts import render

# Create your views here.
from rest_framework import generics
from .models import *
from .serializers import *

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

class ItemListCreate(generics.ListCreateAPIView):
    queryset = Product.objects.all()
    serializer_class = ItemSerializer



class ProductDetailView(generics.RetrieveDestroyAPIView):
    queryset = Product.objects.all().prefetch_related('variations')
    serializer_class = ProductDetailSerializer


    def perform_destroy(self, instance):
        # Delete image from S3 before deleting the DB record
        if instance.image:
            instance.image.delete(save=False)
        instance.delete()



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




# ==============================================================================
# USER REGISTRATION VIEW (SIGNUP)
# ==============================================================================
class RegisterAPIView(APIView):
    def post(self, request):
        username = request.data.get('username')
        email = request.data.get('email')
        password = request.data.get('password')

        # Validation checks
        if not username or not email or not password:
            return Response({"error": "All fields are required"}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(username=username).exists():
            return Response({"error": "Username already taken"}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email=email).exists():
            return Response({"error": "Email already registered"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Create user and hash their password securely
            user = User.objects.create_user(username=username, email=email, password=password)
            # Pre-generate their login token right away
            token, _ = Token.objects.get_or_create(user=user)
            
            return Response({
                "message": "User registered successfully",
                "token": token.key
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

# ==============================================================================
# USER INITIALIZATION VIEW (LOGIN)
# ==============================================================================
class LoginAPIView(APIView):
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        if not username or not password:
            return Response({"error": "Username and password are required"}, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(username=username, password=password)

        if user:
            # Fetch or generate their unique login string token
            token, _ = Token.objects.get_or_create(user=user)
            return Response({"token": token.key}, status=status.HTTP_200_OK)
        else:
            return Response({"non_field_errors": ["Invalid credentials"]}, status=status.HTTP_400_BAD_REQUEST)
