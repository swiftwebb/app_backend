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
