from django.shortcuts import render
from django.http import HttpResponse, HttpResponseRedirect
from rest_framework import generics, viewsets, permissions
from .models import *
from .serializers import *
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
import requests as http_requests
import hmac, hashlib, json, os

PAYSTACK_SECRET = os.getenv('PAYSTACK_SECRET_KEY', '')  # safe fallback so server starts even if missing


# ==============================================================================
# PRODUCTS
# ==============================================================================

class ItemListCreate(generics.ListCreateAPIView):
    queryset = Product.objects.all()
    serializer_class = ItemSerializer


class ProductDetailView(generics.RetrieveDestroyAPIView):
    queryset = Product.objects.all().prefetch_related('variations')
    serializer_class = ProductDetailSerializer

    def perform_destroy(self, instance):
        if instance.image:
            instance.image.delete(save=False)
        instance.delete()


# ==============================================================================
# AUTH
# ==============================================================================

class RegisterAPIView(APIView):
    def post(self, request):
        username = request.data.get('username')
        email    = request.data.get('email')
        password = request.data.get('password')

        if not username or not email or not password:
            return Response({"error": "All fields are required"}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(username=username).exists():
            return Response({"error": "Username already taken"}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(email=email).exists():
            return Response({"error": "Email already registered"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.create_user(username=username, email=email, password=password)
            token, _ = Token.objects.get_or_create(user=user)
            return Response({"message": "User registered successfully", "token": token.key}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class LoginAPIView(APIView):
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        if not username or not password:
            return Response({"error": "Username and password are required"}, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(username=username, password=password)
        if user:
            token, _ = Token.objects.get_or_create(user=user)
            return Response({"token": token.key}, status=status.HTTP_200_OK)
        return Response({"non_field_errors": ["Invalid credentials"]}, status=status.HTTP_400_BAD_REQUEST)


class LogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            request.user.auth_token.delete()
            return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ==============================================================================
# CART
# ==============================================================================

class CartViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return CartItem.objects.filter(user=self.request.user).select_related('variation__product')

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return CartItemReadSerializer
        return CartItemWriteSerializer

    def perform_create(self, serializer):
        variation = serializer.validated_data['variation']
        quantity  = serializer.validated_data.get('quantity', 1)

        cart_item, created = CartItem.objects.get_or_create(
            user=self.request.user,
            variation=variation,
            defaults={'quantity': quantity}
        )

        if not created:
            cart_item.quantity += quantity
            if cart_item.quantity > variation.stock:
                from rest_framework.exceptions import ValidationError
                raise ValidationError(f"Cannot add more. Max stock is {variation.stock}.")
            cart_item.save()


# ==============================================================================
# CHECKOUT (legacy non-Paystack endpoint — kept for reference)
# ==============================================================================

class CheckoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data       = serializer.validated_data
        cart_items = CartItem.objects.filter(user=request.user).select_related('variation__product')

        if not cart_items.exists():
            return Response({"error": "Your cart is empty."}, status=status.HTTP_400_BAD_REQUEST)

        subtotal      = sum(item.quantity * item.variation.product.price for item in cart_items)
        shipping_cost = 0
        grand_total   = subtotal + shipping_cost

        try:
            with transaction.atomic():
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
                cart_items.delete()
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


# ==============================================================================
# ORDERS
# ==============================================================================

class OrderListAPIView(generics.ListAPIView):
    serializer_class   = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related('items')


class VerifyPaymentAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id, user=request.user)
        except Order.DoesNotExist:
            return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "order_id":    order.id,
            "is_paid":     order.is_paid,
            "status":      order.status,
            "grand_total": str(order.grand_total),
        })


# ==============================================================================
# PAYSTACK
# ==============================================================================

class InitializePaymentAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data       = serializer.validated_data
        cart_items = CartItem.objects.filter(user=request.user).select_related('variation__product')

        if not cart_items.exists():
            return Response({"error": "Your cart is empty."}, status=status.HTTP_400_BAD_REQUEST)

        subtotal    = sum(item.quantity * item.variation.product.price for item in cart_items)
        grand_total = subtotal  # add shipping here if needed

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
                    shipping_cost=0,
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

        paystack_res = http_requests.post(
            'https://api.paystack.co/transaction/initialize',
            headers={
                'Authorization': f'Bearer {PAYSTACK_SECRET}',
                'Content-Type': 'application/json',
            },
            json={
                'email':     data['email'],
                'amount':    int(grand_total * 100),  # kobo
                'reference': f'ORDER-{order.id}',
                'metadata':  {'order_id': order.id, 'user_id': request.user.id},
                'callback_url': 'https://app-backend-03wo.onrender.com/api/paystack/callback/',
            },
        )

        if paystack_res.status_code != 200:
            order.delete()
            return Response({"error": "Could not initialize payment. Try again."}, status=status.HTTP_502_BAD_GATEWAY)

        paystack_data = paystack_res.json()['data']
        return Response({
            'order_id':          order.id,
            'authorization_url': paystack_data['authorization_url'],
            'reference':         paystack_data['reference'],
            'access_code':       paystack_data['access_code'],
        }, status=status.HTTP_200_OK)


class PaystackCallbackAPIView(APIView):
    """
    Paystack redirects here after the user completes (or abandons) payment.
    We verify, mark the order paid, then redirect the WebView to an HTTPS
    URL that onNavigationStateChange in the app can detect.
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
            return HttpResponseRedirect(
                'https://app-backend-03wo.onrender.com/api/payment-cancelled/'
            )

        try:
            order_id = int(reference.replace('ORDER-', ''))
            order    = Order.objects.get(id=order_id)
        except (ValueError, Order.DoesNotExist):
            return HttpResponse('<h2>Order not found.</h2>', status=404)

        if not order.is_paid:
            order.is_paid     = True
            order.status      = 'confirmed'
            order.payment_ref = reference
            order.save()
            CartItem.objects.filter(user=order.user).delete()

        # Redirect to HTTPS URL — the app's onNavigationStateChange catches "payment-success"
        return HttpResponseRedirect(
            f'https://app-backend-03wo.onrender.com/api/payment-success/?orderId={order.id}'
        )


class PaystackWebhookAPIView(APIView):
    """
    Server-to-server webhook from Paystack (reliable backup).
    Register this URL in Paystack dashboard → Settings → Webhooks.
    """
    def post(self, request):
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
                order    = Order.objects.get(id=order_id)
                if not order.is_paid:
                    order.is_paid     = True
                    order.status      = 'confirmed'
                    order.payment_ref = reference
                    order.save()
                    CartItem.objects.filter(user=order.user).delete()
            except (ValueError, Order.DoesNotExist):
                pass

        return Response({"status": "ok"})


# ==============================================================================
# PAYMENT RESULT PAGES  (WebView lands here; app catches the URL)
# ==============================================================================

class PaymentSuccessView(APIView):
    def get(self, request):
        return HttpResponse(
            '<html><body style="font-family:sans-serif;text-align:center;padding-top:80px">'
            '<h2>Payment successful!</h2><p>Returning to the app...</p></body></html>'
        )


class PaymentCancelledView(APIView):
    def get(self, request):
        return HttpResponse(
            '<html><body style="font-family:sans-serif;text-align:center;padding-top:80px">'
            '<h2>Payment cancelled.</h2><p>You can close this and try again.</p></body></html>'
        )