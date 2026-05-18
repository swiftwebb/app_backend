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