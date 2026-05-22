from django.shortcuts import render
    from django.http import HttpResponse

# Create your views here.
from rest_framework import generics
from .models import *
from .serializers import *
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
import os
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

# ── View ───────────────────────────────────────────────────────────────────────

from django.db import transaction


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



# ── Add to views.py ────────────────────────────────────────────────────────────
# pip install requests (already in your requirements)
# Add PAYSTACK_SECRET_KEY to your .env and Render environment variables

import requests as http_requests
import hmac, hashlib, json

PAYSTACK_SECRET = os.getenv('PAYSTACK_SECRET_KEY')  # sk_live_... or sk_test_...


class InitializePaymentAPIView(APIView):
    """
    Step 1 — Called when user taps 'Pay now'.
    Creates a pending Order, then asks Paystack for a payment authorization URL.
    Returns the URL to the app which opens it in a WebView/browser.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        cart_items = CartItem.objects.filter(user=request.user).select_related('variation__product')

        if not cart_items.exists():
            return Response({"error": "Your cart is empty."}, status=status.HTTP_400_BAD_REQUEST)

        subtotal     = sum(item.quantity * item.variation.product.price for item in cart_items)
        shipping     = 0
        grand_total  = subtotal + shipping

        try:
            with transaction.atomic():
                order = Order.objects.create(
                    user=request.user,
                    status='pending',
                    full_name=data['full_name'],
                    email=data['email'],
                    phone=data['phone'],
                    address_line1=data['address_line1'],
                    address_line2=data.get('address_line2', ''),
                    city=data['city'],
                    state=data['state'],
                    postal_code=data['postal_code'],
                    country=data.get('country', 'Nigeria'),
                    payment_method='paystack',
                    subtotal=subtotal,
                    shipping_cost=shipping,
                    grand_total=grand_total,
                )
                for cart_item in cart_items:
                    OrderItem.objects.create(
                        order=order,
                        variation=cart_item.variation,
                        product_name=cart_item.variation.product.name,
                        size=cart_item.variation.get_size_display(),
                        color=cart_item.variation.get_color_display(),
                        price_at_purchase=cart_item.variation.product.price,
                        quantity=cart_item.quantity,
                    )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Ask Paystack to create a payment session
        # Amount must be in kobo (multiply by 100)
        paystack_res = http_requests.post(
            'https://api.paystack.co/transaction/initialize',
            headers={
                'Authorization': f'Bearer {PAYSTACK_SECRET}',
                'Content-Type': 'application/json',
            },
            json={
                'email': data['email'],
                'amount': int(grand_total * 100),   # kobo
                'reference': f'ORDER-{order.id}',
                'metadata': {
                    'order_id': order.id,
                    'user_id': request.user.id,
                    'cancel_action': 'https://your-app.com/payment-cancelled',
                },
                'callback_url': f'https://app-backend-03wo.onrender.com/api/paystack/callback/',
            },
        )

        if paystack_res.status_code != 200:
            order.delete()  # rollback — don't leave a ghost order
            return Response({"error": "Could not initialize payment. Try again."}, status=status.HTTP_502_BAD_GATEWAY)

        paystack_data = paystack_res.json()['data']
        return Response({
            'order_id': order.id,
            'authorization_url': paystack_data['authorization_url'],  # open this in WebView
            'reference': paystack_data['reference'],
        }, status=status.HTTP_200_OK)


class PaystackCallbackAPIView(APIView):
    def get(self, request):
        reference = request.GET.get('reference', '')
        if not reference:
            return HttpResponse('<h2>Invalid payment reference.</h2>', status=400)

        verify_res = http_requests.get(
            f'https://api.paystack.co/transaction/verify/{reference}',
            headers={'Authorization': f'Bearer {PAYSTACK_SECRET}'},
        )

        if verify_res.status_code != 200:
            return HttpResponse('<h2>Could not verify payment.</h2>', status=502)

        verify_data = verify_res.json()['data']

        if verify_data['status'] != 'success':
            # ← redirect to a real HTTPS cancel URL
            return HttpResponseRedirect(
                f'https://app-backend-03wo.onrender.com/api/payment-cancelled/'
            )

        try:
            order_id = int(reference.replace('ORDER-', ''))
            order = Order.objects.get(id=order_id)
        except (ValueError, Order.DoesNotExist):
            return HttpResponse('<h2>Order not found.</h2>', status=404)

        if not order.is_paid:
            order.is_paid = True
            order.status = 'confirmed'
            order.payment_ref = reference
            order.save()
            CartItem.objects.filter(user=order.user).delete()

        # ← redirect to a real HTTPS success URL (WebView will catch this)
        return HttpResponseRedirect(
            f'https://app-backend-03wo.onrender.com/api/payment-success/?orderId={order.id}'
        )    """
    Step 2 — Paystack redirects the user here after payment.
    Verifies the transaction and marks the order as paid.
    This is a browser redirect so we return a simple HTML response.
    """
    def get(self, request):
        reference = request.GET.get('reference', '')
        if not reference:
            return HttpResponse('<h2>Invalid payment reference.</h2>', status=400)

        verify_res = http_requests.get(
            f'https://api.paystack.co/transaction/verify/{reference}',
            headers={'Authorization': f'Bearer {PAYSTACK_SECRET}'},
        )

        if verify_res.status_code != 200:
            return HttpResponse('<h2>Could not verify payment.</h2>', status=502)

        verify_data = verify_res.json()['data']

        if verify_data['status'] != 'success':
            return HttpResponse('<h2>Payment was not successful.</h2>', status=400)

        # Extract our order id from the reference (format: ORDER-<id>)
        try:
            order_id = int(reference.replace('ORDER-', ''))
            order = Order.objects.get(id=order_id)
        except (ValueError, Order.DoesNotExist):
            return HttpResponse('<h2>Order not found.</h2>', status=404)

        if not order.is_paid:
            order.is_paid = True
            order.status = 'confirmed'
            order.payment_ref = reference
            order.save()

            # Clear the cart now that payment is confirmed
            CartItem.objects.filter(user=order.user).delete()

        # Redirect the WebView to a deep link your app can catch
        return HttpResponseRedirect(f'myapp://payment-success?orderId={order.id}')


class PaystackWebhookAPIView(APIView):
    """
    Step 3 (optional but recommended) — Paystack sends a server-to-server
    webhook for reliable payment confirmation (handles network drops etc).
    Add this URL in your Paystack dashboard → Settings → Webhooks.
    """
    def post(self, request):
        # Verify the webhook signature
        paystack_sig = request.headers.get('x-paystack-signature', '')
        computed = hmac.new(
            PAYSTACK_SECRET.encode('utf-8'),
            request.body,
            hashlib.sha512,
        ).hexdigest()

        if paystack_sig != computed:
            return Response({"error": "Invalid signature"}, status=status.HTTP_400_BAD_REQUEST)

        payload = json.loads(request.body)
        event   = payload.get('event')

        if event == 'charge.success':
            reference = payload['data']['reference']
            try:
                order_id = int(reference.replace('ORDER-', ''))
                order = Order.objects.get(id=order_id)
                if not order.is_paid:
                    order.is_paid = True
                    order.status  = 'confirmed'
                    order.payment_ref = reference
                    order.save()
                    CartItem.objects.filter(user=order.user).delete()
            except (ValueError, Order.DoesNotExist):
                pass  # Log this in production

        return Response({"status": "ok"})


class VerifyPaymentAPIView(APIView):
    """
    The app calls this after the WebView closes to confirm payment status.
    Avoids relying solely on deep links which can fail.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id, user=request.user)
        except Order.DoesNotExist:
            return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "order_id": order.id,
            "is_paid": order.is_paid,
            "status": order.status,
            "grand_total": str(order.grand_total),
        })





class CartViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    # Filters the data so users can only view items belonging to their own account
    def get_queryset(self):
        return CartItem.objects.filter(user=self.request.user).select_related('variation__product')

    # Dynamically switches serializers based on the incoming request action
    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return CartItemReadSerializer
        return CartItemWriteSerializer

    # Automatically assigns the authenticated user when adding an item to the cart
    def perform_create(self, serializer):
        variation = serializer.validated_data['variation']
        quantity = serializer.validated_data.get('quantity', 1)
        
        cart_item, created = CartItem.objects.get_or_create(
            user=self.request.user,
            variation=variation,
            defaults={'quantity': quantity}
        )
        
        if not created:
            cart_item.quantity += quantity
            if cart_item.quantity > variation.stock:
                # Fix: raise ValidationError directly, not through serializer
                from rest_framework.exceptions import ValidationError
                raise ValidationError(f"Cannot add more. Max stock is {variation.stock}.")
            cart_item.save()











class CheckoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        cart_items = CartItem.objects.filter(user=request.user).select_related('variation__product')

        if not cart_items.exists():
            return Response({"error": "Your cart is empty."}, status=status.HTTP_400_BAD_REQUEST)

        # Calculate totals from live cart
        subtotal = sum(item.quantity * item.variation.product.price for item in cart_items)
        shipping_cost = 0
        grand_total = subtotal + shipping_cost

        try:
            with transaction.atomic():
                # 1. Create the order
                order = Order.objects.create(
                    user=request.user,
                    full_name=data['full_name'],
                    email=data['email'],
                    phone=data['phone'],
                    address_line1=data['address_line1'],
                    address_line2=data.get('address_line2', ''),
                    city=data['city'],
                    state=data['state'],
                    postal_code=data['postal_code'],
                    country=data.get('country', 'Nigeria'),
                    payment_method=data.get('payment_method', 'card'),
                    subtotal=subtotal,
                    shipping_cost=shipping_cost,
                    grand_total=grand_total,
                )

                # 2. Snapshot each cart item into an OrderItem
                for cart_item in cart_items:
                    OrderItem.objects.create(
                        order=order,
                        variation=cart_item.variation,
                        product_name=cart_item.variation.product.name,
                        size=cart_item.variation.get_size_display(),
                        color=cart_item.variation.get_color_display(),
                        price_at_purchase=cart_item.variation.product.price,
                        quantity=cart_item.quantity,
                    )

                # 3. Clear the cart
                cart_items.delete()

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderListAPIView(generics.ListAPIView):
    """Returns the logged-in user's order history."""
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related('items')



class PaymentSuccessView(APIView):
    def get(self, request):
        # WebView catches this URL via onNavigationStateChange
        return HttpResponse('<h2>Payment successful! Returning to app...</h2>')

class PaymentCancelledView(APIView):
    def get(self, request):
        return HttpResponse('<h2>Payment cancelled.</h2>')