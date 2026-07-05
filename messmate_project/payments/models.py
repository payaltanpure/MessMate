from django.db import models
from django.conf import settings
from student.models import Payment as StudentPayment, WalletTransaction

# This app uses existing student.Payment and WalletTransaction models.
# No duplicate models added here to preserve DB schema.
