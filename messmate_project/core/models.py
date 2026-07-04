from django.db import models
from vendor.models import Mess

class DemandForecast(models.Model):
    mess = models.ForeignKey(Mess, on_delete=models.CASCADE, related_name='demand_forecasts')
    date = models.DateField()
    predicted_orders = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Demand Forecast for {self.mess.mess_name} on {self.date}: {self.predicted_orders} orders"


class FoodWastePrediction(models.Model):
    mess = models.ForeignKey(Mess, on_delete=models.CASCADE, related_name='waste_predictions')
    date = models.DateField()
    predicted_excess_meals = models.IntegerField(default=0)
    predicted_shortage_meals = models.IntegerField(default=0)
    suggested_raw_material_modifier = models.DecimalField(max_digits=4, decimal_places=2, default=1.00) # e.g. 0.9 for reduce by 10%
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Waste Prediction for {self.mess.mess_name} on {self.date}"
