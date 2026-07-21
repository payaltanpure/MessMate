from django.test import TestCase

from core.ai_services import recommend_messes, predict_meal_demand, train_demand_model, forecast_demand, predict_food_waste
from accounts.models import User
from vendor.models import Meal, Mess
from student.models import Order, OrderItem, Subscription


class AIFeatureTests(TestCase):
    def setUp(self):
        self.vendor = User.objects.create_user(
            username='vendorai',
            email='vendorai@example.com',
            password='StrongPass123',
            role='vendor',
        )
        self.student = User.objects.create_user(
            username='studentai',
            email='studentai@example.com',
            password='StrongPass123',
            role='student',
        )
        self.mess = Mess.objects.create(
            vendor=self.vendor,
            mess_name='AI Mess',
            address='AI Street',
            contact_number='2222222222',
            description='AI test mess',
            diet_type='both',
            location_name='Hostel',
            distance=1.0,
            monthly_price_both=150.0,
            average_rating=4.2,
        )
        self.meal = Meal.objects.create(
            mess=self.mess,
            meal_type='lunch',
            name='AI Meal',
            menu_items='Rice, Dal',
            price=100.0,
            is_available=True,
        )
        Subscription.objects.create(
            student=self.student,
            mess=self.mess,
            plan_type='both',
            start_date='2026-01-01',
            end_date='2026-01-31',
            price_paid='150.00',
            status='active',
            remaining_days=30,
            pause_remaining_days=30,
        )

    def test_recommend_messes_returns_payload(self):
        result = recommend_messes(student_pref='veg')
        self.assertIn('best_mess', result)
        self.assertIn('all_recommendations', result)

    def test_train_demand_model_creates_payload(self):
        payload = train_demand_model()
        self.assertIn('mode', payload)

    def test_predict_meal_demand_returns_values(self):
        prediction = predict_meal_demand(self.meal.id)
        self.assertIn('tomorrow', prediction)
        self.assertIn('weekly', prediction)
        self.assertIn('monthly', prediction)

    def test_forecast_demand_returns_values(self):
        forecast = forecast_demand(self.mess.id)
        self.assertIn('tomorrow', forecast)
        self.assertIn('weekly', forecast)
        self.assertIn('monthly', forecast)

    def test_predict_food_waste_returns_structured_output(self):
        waste = predict_food_waste(self.mess.id)
        self.assertIn('expected_diners', waste)
        self.assertIn('recommendation', waste)
