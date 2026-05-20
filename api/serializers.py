from rest_framework import serializers
from .models import *

from rest_framework import viewsets, permissions, status
from rest_framework.response import Response

class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = '__all__'


class ProductVariationSerializer(serializers.ModelSerializer):
    # Displays readable choices instead of raw database values/hex codes
    size_display = serializers.CharField(source='get_size_display', read_only=True)
    color_display = serializers.CharField(source='get_color_display', read_only=True)

    class Meta:
        model = ProductVariation
        fields = ['id', 'size', 'size_display', 'color', 'color_display', 'stock']

class ProductDetailSerializer(serializers.ModelSerializer):
    # This automatically includes all variations tied to this product
    variations = ProductVariationSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = ['id', 'name', 'description', 'price', 'image', 'created_at', 'variations']




class CartItemReadSerializer(serializers.ModelSerializer):
    # Pull details from parent variation and grandparent product models
    product_name = serializers.CharField(source='variation.product.name', read_only=True)
    product_price = serializers.DecimalField(source='variation.product.price', max_digits=10, decimal_places=2, read_only=True)
    product_image = serializers.ImageField(source='variation.product.image', read_only=True)
    size = serializers.CharField(source='variation.get_size_display', read_only=True)
    color = serializers.CharField(source='variation.get_color_display', read_only=True)
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ['id', 'variation', 'product_name', 'product_price', 'product_image', 'size', 'color', 'quantity', 'subtotal']

    def get_subtotal(self, obj):
        return obj.quantity * obj.variation.product.price


class CartItemWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CartItem
        fields = ['variation', 'quantity']

    def validate(self, data):
        # Prevent adding more items to the cart than what is physically available in stock
        variation = data.get('variation')
        quantity = data.get('quantity', 1)
        
        if quantity > variation.stock:
            raise serializers.ValidationError(f"Only {variation.stock} units available in stock.")
        return data







# ── Serializers ────────────────────────────────────────────────────────────────

class OrderItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'product_name', 'size', 'color', 'price_at_purchase', 'quantity', 'subtotal']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'status', 'full_name', 'email', 'phone',
            'address_line1', 'address_line2', 'city', 'state',
            'postal_code', 'country', 'subtotal', 'shipping_cost',
            'grand_total', 'payment_method', 'is_paid', 'created_at', 'items',
        ]
        read_only_fields = ['id', 'status', 'subtotal', 'shipping_cost', 'grand_total', 'is_paid', 'created_at', 'items']


class CheckoutSerializer(serializers.Serializer):
    """Accepts shipping address, creates Order + OrderItems from the user's cart."""
    full_name     = serializers.CharField(max_length=255)
    email         = serializers.EmailField()
    phone         = serializers.CharField(max_length=20)
    address_line1 = serializers.CharField(max_length=255)
    address_line2 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    city          = serializers.CharField(max_length=100)
    state         = serializers.CharField(max_length=100)
    postal_code   = serializers.CharField(max_length=20)
    country       = serializers.CharField(max_length=100, default='Nigeria')
    payment_method = serializers.CharField(max_length=50, default='card')