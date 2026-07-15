from django import forms
from vendor.models import Mess, Meal


class MessAdminForm(forms.ModelForm):
    class Meta:
        model = Mess
        fields = [
            'mess_name',
            'vendor',
            'address',
            'contact_number',
            'description',
            'diet_type',
            'location_name',
            'distance',
            'monthly_price_lunch',
            'monthly_price_dinner',
            'monthly_price_both',
            'daily_tiffin_price',
            'is_active',
            'image',
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class MealAdminForm(forms.ModelForm):
    class Meta:
        model = Meal
        fields = [
            'mess',
            'meal_type',
            'name',
            'menu_items',
            'price',
            'is_available',
            'image',
        ]
        widgets = {
            'menu_items': forms.Textarea(attrs={'rows': 3}),
        }
