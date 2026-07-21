from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('vendor', 'Vendor'),
        ('student', 'Student'),
        ('delivery', 'Delivery Boy'),
    )

    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='student')
    phone = models.CharField(max_length=15, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    email_verified = models.BooleanField(default=False)
    fcm_token = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    photo = models.ImageField(upload_to='profiles/students/', blank=True, null=True)
    wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    cashback_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return f"Student: {self.user.username}"


class VendorProfile(models.Model):
    VERIFICATION_CHOICES = (
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('suspended', 'Suspended'),
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='vendor_profile')
    business_name = models.CharField(max_length=150)
    business_address = models.TextField()
    contact_number = models.CharField(max_length=15)
    verification_status = models.CharField(max_length=20, choices=VERIFICATION_CHOICES, default='pending')
    gst_number = models.CharField(max_length=15, blank=True, null=True)
    fssai_license = models.CharField(max_length=14, blank=True, null=True)
    documents = models.FileField(upload_to='documents/vendors/', blank=True, null=True)

    def __str__(self):
        return f"Vendor: {self.business_name} ({self.get_verification_status_display()})"


class DeliveryBoyProfile(models.Model):
    VERIFICATION_CHOICES = (
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )
    VEHICLE_TYPE_CHOICES = (
        ('bike', 'Bike'),
        ('cycle', 'Cycle'),
        ('scooter', 'Scooter'),
        ('other', 'Other'),
    )
    AVAILABILITY_CHOICES = (
        ('available', 'Available'),
        ('busy', 'Busy'),
        ('offline', 'Offline'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='delivery_profile')
    photo = models.ImageField(upload_to='profiles/delivery_boys/', blank=True, null=True)
    vehicle_type = models.CharField(max_length=20, choices=VEHICLE_TYPE_CHOICES, default='bike')
    vehicle_number = models.CharField(max_length=20, blank=True, default='')
    emergency_contact = models.CharField(max_length=15, blank=True, default='')
    availability_status = models.CharField(max_length=20, choices=AVAILABILITY_CHOICES, default='offline')
    verification_status = models.CharField(max_length=20, choices=VERIFICATION_CHOICES, default='pending')
    license_number = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        return f"Delivery Boy: {self.user.username} ({self.get_verification_status_display()})"


