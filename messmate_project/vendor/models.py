from django.db import models
from django.conf import settings

class Mess(models.Model):
    DIET_CHOICES = (
        ('veg', 'Veg Only'),
        ('non-veg', 'Non-Veg Only'),
        ('both', 'Veg & Non-Veg'),
    )

    vendor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='messes')
    mess_name = models.CharField(max_length=100)
    address = models.TextField()
    contact_number = models.CharField(max_length=15)
    description = models.TextField(blank=True)
    diet_type = models.CharField(max_length=10, choices=DIET_CHOICES, default='both')
    
    # Location and distance metrics (distance from hostel area in km)
    location_name = models.CharField(max_length=150, default='Hostel Campus')
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    distance = models.FloatField(default=1.0) # in km
    
    # Pricing for subscriptions
    monthly_price_lunch = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    monthly_price_dinner = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    monthly_price_both = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    
    # Pricing for single order tiffin
    daily_tiffin_price = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    
    # Rating & verification
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    is_active = models.BooleanField(default=True)
    image = models.ImageField(upload_to='messes/', blank=True, null=True)

    def __str__(self):
        return self.mess_name

    def update_rating(self):
        # Calculated automatically from reviews
        reviews = self.reviews.all()
        if reviews.exists():
            avg = sum([r.rating for r in reviews]) / reviews.count()
            self.average_rating = round(avg, 2)
        else:
            self.average_rating = 0.00
        self.save()


class Meal(models.Model):
    MEAL_TYPES = (
        ('breakfast', 'Breakfast'),
        ('lunch', 'Lunch'),
        ('dinner', 'Dinner'),
    )

    mess = models.ForeignKey(Mess, on_delete=models.CASCADE, related_name='meals')
    meal_type = models.CharField(max_length=20, choices=MEAL_TYPES)
    name = models.CharField(max_length=100, default='Daily Special Tiffin')
    menu_items = models.TextField() # e.g. "Roti, Dal, Paneer, Rice"
    price = models.DecimalField(max_digits=6, decimal_places=2)
    is_available = models.BooleanField(default=True)
    image = models.ImageField(upload_to='meals/', blank=True, null=True)

    def __str__(self):
        return f"{self.mess.mess_name} - {self.meal_type} ({self.name})"

    @property
    def created_date(self):
        return getattr(self, 'created_at', None)
