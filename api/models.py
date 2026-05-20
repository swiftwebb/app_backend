from django.db import models

from django.contrib.auth.models import User
from django.db import models

class Product(models.Model):
    name = models.CharField(max_length=255, default="jacket")
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=29.99)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class ProductVariation(models.Model):
    # Size Choices
    SIZE_CHOICES = [
        ('S', 'Small'),
        ('M', 'Medium'),
        ('L', 'Large'),
        ('XL', 'Extra Large'),
    ]
  
  
  
 

  
    # Color Choices (Storing names/hex codes)
    # Color Choices (Storing names/hex codes)
    COLOR_CHOICES = [
        ("#F3F4F6", 'White'),
        ("#B11D1D", 'Red'),
        ("#1F44A3", 'Blue'),
        ("#9F632A", 'Brown'),
        ("#1D752B", 'Green'),
        ("#333333", 'Black'),  # <--- Added the comma here!
    ]


        
    

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variations')

    size = models.CharField(max_length=2, choices=SIZE_CHOICES)
    color = models.CharField(max_length=10, choices=COLOR_CHOICES)
    stock = models.IntegerField(default=1)  # Essential for e-commerce tracking

    class Meta:
        # Prevents duplicate size/color combos for the same product
        unique_together = ('product', 'size', 'color') 

    def __str__(self):
        return f"{self.product.name} - {self.get_size_display()} / {self.get_color_display()}"




class CartItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cart')
    # Link directly to the specific variation, NOT the base product
    variation = models.ForeignKey(ProductVariation, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.user.username} - {self.variation} (Qty: {self.quantity})"





# Add these to your existing models.py

class Order(models.Model):
    STATUS_CHOICES = [
        ('pending',    'Pending'),
        ('confirmed',  'Confirmed'),
        ('shipped',    'Shipped'),
        ('delivered',  'Delivered'),
        ('cancelled',  'Cancelled'),
    ]

    user            = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Shipping address snapshot
    full_name       = models.CharField(max_length=255)
    email           = models.EmailField()
    phone           = models.CharField(max_length=20)
    address_line1   = models.CharField(max_length=255)
    address_line2   = models.CharField(max_length=255, blank=True)
    city            = models.CharField(max_length=100)
    state           = models.CharField(max_length=100)
    postal_code     = models.CharField(max_length=20)
    country         = models.CharField(max_length=100, default='Nigeria')

    # Totals snapshot (never recalculate from live prices)
    subtotal        = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_cost   = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    grand_total     = models.DecimalField(max_digits=10, decimal_places=2)

    # Payment
    payment_method  = models.CharField(max_length=50, default='card')
    payment_ref     = models.CharField(max_length=255, blank=True)  # Stripe/Paystack ref
    is_paid         = models.BooleanField(default=False)

    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order #{self.id} — {self.user.username} ({self.status})"


class OrderItem(models.Model):
    """Snapshot of each cart item at the moment of purchase."""
    order           = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    variation       = models.ForeignKey(ProductVariation, on_delete=models.SET_NULL, null=True)

    # Snapshot fields — kept even if the variation is deleted later
    product_name    = models.CharField(max_length=255)
    size            = models.CharField(max_length=10)
    color           = models.CharField(max_length=20)
    price_at_purchase = models.DecimalField(max_digits=10, decimal_places=2)
    quantity        = models.IntegerField()

    @property
    def subtotal(self):
        return self.price_at_purchase * self.quantity

    def __str__(self):
        return f"{self.product_name} x{self.quantity} (Order #{self.order.id})"