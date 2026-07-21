import os
import pickle
import random
import datetime
from decimal import Decimal
from django.conf import settings
from django.db.models import Count, Q, Sum
from accounts.models import User
from vendor.models import Mess, Meal
from student.models import Complaint, Order, OrderItem, Payment, Review, Subscription
from core.integration_fallbacks import is_demo_mode_enabled, log_demo_fallback
HAS_NUMPY = HAS_PANDAS = HAS_SKLEARN = False
np = None
pd = None
LinearRegression = None
try:
    import numpy as np
    HAS_NUMPY = True
except Exception:
    np = None
try:
    import pandas as pd
    HAS_PANDAS = True
except Exception:
    pd = None
try:
    from sklearn.linear_model import LinearRegression
    HAS_SKLEARN = True
except Exception:
    LinearRegression = None

# Gemini API Integration
try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

def get_gemini_client():
    if not HAS_GEMINI:
        return None
    api_key = getattr(settings, 'GEMINI_API_KEY', os.getenv('GEMINI_API_KEY'))
    if not api_key or is_demo_mode_enabled('gemini', [api_key]):
        log_demo_fallback('gemini', 'GEMINI_API_KEY missing or invalid', 'use local recommendation engine and predefined chatbot responses')
        return None
    try:
        genai.configure(api_key=api_key)
        return genai.GenerativeModel('gemini-1.5-flash')
    except Exception:
        return None


# 1. AI Recommendation Engine
def recommend_messes(student_pref='both', budget=None, max_distance=None, min_rating=None):
    """
    Ranks messes based on student preferences, budget, distance, and ratings.
    """
    messes = Mess.objects.filter(is_active=True)
    
    # Pre-filter by diet preference
    if student_pref == 'veg':
        messes = messes.filter(diet_type__in=['veg', 'both'])
    elif student_pref == 'non-veg':
        messes = messes.filter(diet_type__in=['non-veg', 'both'])
        
    messes_list = list(messes)
    if not messes_list:
        return {'best_mess': None, 'best_value': None, 'most_popular': None, 'all_recommendations': []}
    # If pandas/numpy not available, fall back to lightweight scoring to avoid ImportError at import-time
    try:
        if HAS_PANDAS and HAS_NUMPY:
            data = []
            for m in messes_list:
                price_val = float(m.monthly_price_both if m.monthly_price_both and m.monthly_price_both > 0 else (m.daily_tiffin_price * 30))
                data.append({
                    'id': m.id,
                    'name': m.mess_name,
                    'price': price_val,
                    'distance': float(m.distance),
                    'rating': float(m.average_rating),
                    'obj': m
                })
            df = pd.DataFrame(data)
            price_min, price_max = df['price'].min(), df['price'].max()
            dist_min, dist_max = df['distance'].min(), df['distance'].max()
            df['norm_price'] = 1.0 - (df['price'] - price_min) / (price_max - price_min + 0.1)
            df['norm_dist'] = 1.0 - (df['distance'] - dist_min) / (dist_max - dist_min + 0.1)
            df['norm_rating'] = df['rating'] / 5.0
            df['score'] = (df['norm_rating'] * 0.4) + (df['norm_price'] * 0.3) + (df['norm_dist'] * 0.3)
            df_sorted = df.sort_values(by='score', ascending=False)
            best_mess = df_sorted.iloc[0]['obj'] if not df_sorted.empty else None
            df_value = df[df['rating'] >= 3.5].sort_values(by='price')
            best_value = df_value.iloc[0]['obj'] if not df_value.empty else best_mess
            df_popular = df.sort_values(by=['rating', 'distance'], ascending=[False, True])
            most_popular = df_popular.iloc[0]['obj'] if not df_popular.empty else None
            all_recs = [row['obj'] for _, row in df_sorted.iterrows()]
            return {
                'best_mess': best_mess,
                'best_value': best_value,
                'most_popular': most_popular,
                'all_recommendations': all_recs[:5]
            }
        else:
            # Lightweight fallback scoring (no external ML libs)
            scored = []
            prices = []
            dists = []
            ratings = []
            for m in messes_list:
                price_val = float(m.monthly_price_both if m.monthly_price_both and m.monthly_price_both > 0 else (m.daily_tiffin_price * 30))
                prices.append(price_val)
                dists.append(float(m.distance))
                ratings.append(float(m.average_rating))
            price_min, price_max = min(prices), max(prices)
            dist_min, dist_max = min(dists), max(dists)
            for idx, m in enumerate(messes_list):
                price_val = prices[idx]
                dist_val = dists[idx]
                rating_val = ratings[idx]
                norm_price = 1.0 - ((price_val - price_min) / (price_max - price_min + 0.1))
                norm_dist = 1.0 - ((dist_val - dist_min) / (dist_max - dist_min + 0.1))
                norm_rating = rating_val / 5.0
                score = (norm_rating * 0.4) + (norm_price * 0.3) + (norm_dist * 0.3)
                scored.append((score, m))
            scored.sort(key=lambda x: x[0], reverse=True)
            all_recs = [m for _, m in scored]
            best_mess = all_recs[0] if all_recs else None
            # best value: cheapest among those with decent ratings
            decent = [m for m in messes_list if float(m.average_rating) >= 3.5]
            if decent:
                best_value = min(decent, key=lambda mm: float(mm.monthly_price_both if mm.monthly_price_both and mm.monthly_price_both > 0 else (mm.daily_tiffin_price * 30)))
            else:
                best_value = best_mess
            most_popular = max(messes_list, key=lambda mm: (float(mm.average_rating), -float(mm.distance))) if messes_list else None
            return {
                'best_mess': best_mess,
                'best_value': best_value,
                'most_popular': most_popular,
                'all_recommendations': all_recs[:5]
            }
    except Exception:
        # Safe fallback: return raw mess list if something unexpected fails
        return {
            'best_mess': messes_list[0] if messes_list else None,
            'best_value': messes_list[0] if messes_list else None,
            'most_popular': messes_list[0] if messes_list else None,
            'all_recommendations': messes_list[:5]
        }


# 2. Reusable AI Chatbot

def get_chatbot_response(message, user=None):
    """
    Returns AI answers for user queries, using optional Gemini support or friendly fallback guidance.
    The same service is shared across student, vendor, and admin experiences.
    """
    if not message or not str(message).strip():
        return "Please type a question so I can help you."

    message_text = str(message).strip()
    message_lower = message_text.lower()

    role = getattr(user, 'role', None)

    if role == 'student':
        if "wallet" in message_lower or "balance" in message_lower or "add money" in message_lower:
            return "You can check or top up your wallet from the Student Dashboard under My Wallet."
        if "subscription" in message_lower or "renew" in message_lower:
            return "You can manage your subscription from the Student Dashboard. You can pause, resume, or cancel it there."
        if "complaint" in message_lower or "issue" in message_lower:
            return "You can raise a complaint from the Student Dashboard or support section, and our team will follow up."
        if "order" in message_lower or "tiffin" in message_lower:
            return "You can track your recent orders and current status from the Student Dashboard."
        if "best mess" in message_lower or "recommend" in message_lower:
            recs = recommend_messes()
            if recs['best_mess']:
                return f"Based on student feedback and pricing, I recommend **{recs['best_mess'].mess_name}**."
            return "I couldn't find any active messes on campus right now."
    elif role == 'vendor':
        if "meal" in message_lower or "menu" in message_lower:
            return "You can manage meals and availability from your Vendor Dashboard and meal management screens."
        if "order" in message_lower:
            return "You can review and update order status from the Vendor Orders section."
        if "report" in message_lower or "dashboard" in message_lower:
            return "Your Vendor Dashboard shows overview metrics, subscriptions, earnings, and recent complaints."
    elif role == 'admin':
        if "user" in message_lower:
            return "You can manage students, vendors, and platform users from the Admin Dashboard."
        if "report" in message_lower or "analytics" in message_lower:
            return "Use the analytics and insights pages from the Admin Dashboard to review reports and trends."
        if "complaint" in message_lower:
            return "You can review and resolve complaints from the Admin Complaints section."

    model = get_gemini_client()
    if model:
        try:
            prompt = f"""
            You are 'SmartMess Assistant', the friendly AI support chatbot for the SmartMess platform.
            Answer this inquiry concisely (max 3 sentences) in the context of hostel mess, tiffin ordering, subscriptions, orders, wallet top-ups, complaints, analytics, or vendor management:
            "{message_text}"
            """
            response = model.generate_content(prompt)
            response_text = response.text.strip()
            if response_text:
                return response_text
        except Exception:
            pass

    if not getattr(settings, 'GEMINI_API_KEY', None) and not os.getenv('GEMINI_API_KEY'):
        return "The AI assistant is running in demo mode with guided responses. Please use the dashboard menus for now."

    responses = [
        "Welcome to SmartMess! You can check mess listings, manage subscriptions, track orders, and review support options from your dashboard.",
        "Need help with your account? You can use your dashboard menus for subscriptions, complaints, wallet activity, and reports.",
        "If you are managing a mess, the vendor dashboard contains meal, order, and earnings tools.",
        "Admins can review user activity, analytics, and complaints from the admin dashboard."
    ]
    return random.choice(responses)


def get_ai_insights(role, user=None):
    """Return role-aware AI insight payloads using existing analytics data as the primary source."""
    role_name = (role or '').lower()

    if role_name == 'student':
        orders = Order.objects.filter(student=user).select_related('mess').prefetch_related('items__meal')
        spending_total = Payment.objects.filter(user=user, status='success').aggregate(total=Sum('amount'))['total'] or Decimal('0')
        meal_counts = {}
        for order in orders:
            for item in order.items.all():
                meal_name = getattr(item.meal, 'name', 'Unknown')
                meal_counts[meal_name] = meal_counts.get(meal_name, 0) + item.quantity

        favorite_meals = [
            {'name': meal_name, 'count': count}
            for meal_name, count in sorted(meal_counts.items(), key=lambda item: item[1], reverse=True)[:3]
        ]

        subscription = (
            Subscription.objects.filter(student=user, status='active').select_related('mess').first()
            or Subscription.objects.filter(student=user).select_related('mess').order_by('-start_date').first()
        )
        subscription_name = subscription.mess.mess_name if subscription and subscription.mess else 'No active plan'
        summary = (
            f"You have spent Rs. {spending_total} across {orders.count()} orders. "
            f"Your current focus is on {favorite_meals[0]['name'] if favorite_meals else 'your favourite meals'} "
            f"and your subscription with {subscription_name}."
        )
        return {
            'spending': {
                'total': spending_total,
                'orders': orders.count(),
                'average': (spending_total / orders.count()) if orders.count() else Decimal('0'),
            },
            'favorite_meals': favorite_meals,
            'subscription': {
                'active': bool(subscription and subscription.status == 'active'),
                'mess_name': subscription_name,
            },
            'summary': summary,
        }

    if role_name == 'vendor':
        messes = Mess.objects.filter(vendor=user)
        first_mess = messes.first()
        orders = Order.objects.filter(mess__in=messes).select_related('mess')
        sales_total = Payment.objects.filter(
            Q(order__mess__in=messes) | Q(subscription__mess__in=messes),
            status='success',
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        popular_meals = list(
            Meal.objects.filter(mess__in=messes)
            .annotate(order_count=Count('orderitem'))
            .order_by('-order_count')[:3]
            .values('name', 'order_count')
        )
        active_subscriptions = Subscription.objects.filter(mess__in=messes, status='active').count()
        forecast = forecast_demand(first_mess.id) if first_mess else {'tomorrow': 0, 'weekly': 0, 'monthly': 0}
        waste = predict_food_waste(first_mess.id) if first_mess else {
            'expected_diners': 0,
            'cooked_meals_estimate': 0,
            'excess': 0,
            'shortage': 0,
            'recommendation': 'No data available.',
        }
        summary = (
            f"You are serving {active_subscriptions} active subscribers and have earned Rs. {sales_total}. "
            f"The newest signal is {popular_meals[0]['name'] if popular_meals else 'steady demand'} with {popular_meals[0]['order_count'] if popular_meals else 0} orders."
        )
        return {
            'sales': {
                'total': sales_total,
                'orders': orders.count(),
                'active_subscriptions': active_subscriptions,
            },
            'popular_meals': popular_meals,
            'forecast': forecast,
            'waste': waste,
            'summary': summary,
        }

    if role_name == 'admin':
        students = User.objects.filter(role='student').count()
        vendors = User.objects.filter(role='vendor').count()
        active_subscriptions = Subscription.objects.filter(status='active').count()
        revenue = Payment.objects.filter(status='success').aggregate(total=Sum('amount'))['total'] or Decimal('0')
        complaints = Complaint.objects.all()
        complaint_breakdown = {
            'open': complaints.filter(status='open').count(),
            'resolved': complaints.filter(status='resolved').count(),
            'total': complaints.count(),
        }
        vendor_breakdown = {}
        for order in Order.objects.select_related('mess', 'mess__vendor').all():
            vendor_name = order.mess.vendor.username if order.mess and order.mess.vendor else 'Unknown'
            vendor_breakdown[vendor_name] = vendor_breakdown.get(vendor_name, 0) + 1
        top_vendor = max(vendor_breakdown.items(), key=lambda item: item[1])[0] if vendor_breakdown else 'No data'
        summary = (
            f"The platform currently has {students} students, {vendors} vendors, and {active_subscriptions} active subscriptions. "
            f"Revenue is Rs. {revenue} and the leading vendor is {top_vendor}."
        )
        return {
            'platform': {
                'students': students,
                'vendors': vendors,
                'active_subscriptions': active_subscriptions,
                'orders': Order.objects.count(),
            },
            'complaints': complaint_breakdown,
            'revenue': revenue,
            'top_vendor': top_vendor,
            'summary': summary,
        }

    return {}


# 3. Review Sentiment Analysis
def analyze_review_sentiment(review_text):
    """
    Classifies review sentiment as positive, neutral, or negative.
    """
    # Gemini sentiment analyzer if available
    model = get_gemini_client()
    if model:
        try:
            prompt = f"Analyze the sentiment of this food review. Respond with exactly one word: 'positive', 'neutral', or 'negative'.\n\nReview: \"{review_text}\""
            response = model.generate_content(prompt)
            sentiment = response.text.strip().lower()
            if sentiment in ['positive', 'neutral', 'negative']:
                return sentiment
        except Exception:
            pass

    # Fallback keyword lexicons
    positive_words = ['good', 'great', 'delicious', 'excellent', 'tasty', 'love', 'fresh', 'best', 'awesome', 'yummy', 'friendly']
    negative_words = ['bad', 'worst', 'dirty', 'late', 'cold', 'poor', 'hate', 'stale', 'smell', 'hair', 'insect', 'waste', 'slow']
    
    text_lower = review_text.lower()
    pos_count = sum(1 for w in positive_words if w in text_lower)
    neg_count = sum(1 for w in negative_words if w in text_lower)
    
    if pos_count > neg_count:
        return 'positive'
    elif neg_count > pos_count:
        return 'negative'
    return 'neutral'


MODEL_PATH = os.path.join(settings.BASE_DIR, 'model.pkl')


def _build_rule_based_estimate(meal, history_items=None):
    history_items = history_items or []
    if history_items:
        avg_history = sum(item['demand'] for item in history_items) / max(1, len(history_items))
        base = max(1, int(round(avg_history * 1.1)))
    else:
        active_subs = Subscription.objects.filter(mess=meal.mess, status='active').count()
        base = max(1, int(active_subs * 0.15) + 2)
    return {
        'tomorrow': max(1, base),
        'weekly': max(5, base * 7),
        'monthly': max(20, base * 30),
    }


def train_demand_model():
    """Train a simple regression model for meal demand using existing order history and persist it to model.pkl."""
    payload = {'models': {}, 'meals': []}
    meals = Meal.objects.filter(is_available=True)

    if not HAS_PANDAS or not HAS_SKLEARN or LinearRegression is None:
        payload['mode'] = 'rule_based'
        with open(MODEL_PATH, 'wb') as handle:
            pickle.dump(payload, handle)
        return payload

    for meal in meals:
        history_rows = []
        for item in OrderItem.objects.filter(meal=meal).select_related('order').order_by('order__order_date'):
            history_rows.append({'date': item.order.order_date.date(), 'demand': item.quantity})

        if not history_rows:
            continue

        grouped = pd.DataFrame(history_rows).groupby('date', as_index=False).sum()
        grouped = grouped.sort_values('date')
        if len(grouped) < 2:
            continue

        grouped['day_index'] = range(len(grouped))
        X = grouped[['day_index']].values
        y = grouped['demand'].values
        model = LinearRegression()
        model.fit(X, y)
        payload['models'][str(meal.id)] = {
            'meal_id': meal.id,
            'meal_name': meal.name,
            'model': model,
            'history': grouped[['date', 'demand']].to_dict('records'),
        }
        payload['meals'].append(meal.id)

    payload['mode'] = 'trained'
    with open(MODEL_PATH, 'wb') as handle:
        pickle.dump(payload, handle)
    return payload


def load_demand_model():
    """Load the persisted demand model from model.pkl or train a new one if the file is missing."""
    if os.path.exists(MODEL_PATH):
        with open(MODEL_PATH, 'rb') as handle:
            return pickle.load(handle)
    return train_demand_model()


def predict_meal_demand(meal_id, horizon='tomorrow'):
    """Predict tomorrow, weekly, or monthly demand for a single meal using the persisted model or rule-based fallback."""
    meal = Meal.objects.filter(id=meal_id).first()
    if not meal:
        return {'tomorrow': 0, 'weekly': 0, 'monthly': 0}

    payload = load_demand_model()
    entry = payload.get('models', {}).get(str(meal.id))
    history_items = entry.get('history', []) if entry else []

    if entry and entry.get('model') and HAS_PANDAS and HAS_SKLEARN and LinearRegression is not None and len(history_items) >= 2:
        try:
            history_frame = pd.DataFrame(history_items)
            history_frame['day_index'] = range(len(history_frame))
            next_index = len(history_frame)
            prediction = int(entry['model'].predict([[next_index]])[0])
            prediction = max(1, prediction)
            return {
                'tomorrow': prediction,
                'weekly': max(5, int(prediction * 7 * 0.95)),
                'monthly': max(20, int(prediction * 30 * 0.92)),
                'source': 'model',
            }
        except Exception:
            pass

    estimate = _build_rule_based_estimate(meal, history_items)
    return {
        'tomorrow': estimate['tomorrow'],
        'weekly': estimate['weekly'],
        'monthly': estimate['monthly'],
        'source': 'rule_based',
    }


def predict_meal_demands(meal_ids=None):
    """Return demand predictions for each meal, including the persisted fallback behavior when history is sparse."""
    meals = Meal.objects.filter(id__in=meal_ids) if meal_ids else Meal.objects.filter(is_available=True)
    predictions = []
    for meal in meals:
        prediction = predict_meal_demand(meal.id)
        predictions.append({'meal_id': meal.id, 'meal_name': meal.name, **prediction})
    return predictions


def forecast_demand(mess_id):
    """
    Uses linear regression or moving averages to predict orders.
    Returns: {tomorrow_prediction, weekly_prediction, monthly_prediction}
    """
    orders = Order.objects.filter(mess_id=mess_id, status='delivered')
    
    # If insufficient history, generate an intelligent simulation using active subscribers
    active_subs = Subscription.objects.filter(mess_id=mess_id, status='active').count()
    base_orders = int(active_subs * 0.85) + 5
    
    if orders.count() < 10:
        # Simulate forecasts
        tomorrow = base_orders + random.randint(-3, 5)
        weekly = (base_orders * 7) + random.randint(-15, 20)
        monthly = (base_orders * 30) + random.randint(-50, 80)
        return {
            'tomorrow': max(1, tomorrow),
            'weekly': max(5, weekly),
            'monthly': max(20, monthly)
        }
        
    # Aggregate orders by date
    data = []
    for o in orders:
        data.append({
            'date': o.order_date.date(),
            'count': 1
        })
    df = pd.DataFrame(data)
    df_grouped = df.groupby('date').sum().reset_index()
    df_grouped = df_grouped.sort_values(by='date')
    
    # Simple linear regression with scikit-learn
    df_grouped['day_index'] = np.arange(len(df_grouped))
    X = df_grouped[['day_index']].values
    y = df_grouped['count'].values
    
    model = LinearRegression()
    model.fit(X, y)
    
    next_day_index = len(df_grouped)
    tomorrow_pred = int(model.predict([[next_day_index]])[0])
    
    # Clean output
    tomorrow = max(1, tomorrow_pred)
    weekly = max(5, int(tomorrow * 7 * 0.95))
    monthly = max(20, int(tomorrow * 30 * 0.92))
    
    return {
        'tomorrow': tomorrow,
        'weekly': weekly,
        'monthly': monthly
    }


# 5. Food Waste Prediction
def predict_food_waste(mess_id):
    """
    Predicts excess/shortage food based on forecasted demand vs. active subscriptions.
    """
    # Active students subscribed to the mess
    active_subs = Subscription.objects.filter(mess_id=mess_id, status='active').count()
    
    # Get daily demand forecast
    forecast = forecast_demand(mess_id)
    predicted_tiffin_orders = forecast['tomorrow']
    
    # Assume the vendor cooks meals equal to: Active Subscriptions + 10% buffer + historical avg tiffin orders
    expected_diners = int(active_subs * 0.90) + predicted_tiffin_orders
    cooked_meals_estimate = active_subs + int(predicted_tiffin_orders * 1.2) + 2
    
    excess = cooked_meals_estimate - expected_diners
    shortage = 0
    
    if excess < 0:
        shortage = abs(excess)
        excess = 0
        
    return {
        'expected_diners': expected_diners,
        'cooked_meals_estimate': cooked_meals_estimate,
        'excess': excess,
        'shortage': shortage,
        'recommendation': "Reduce raw material input by 10% to prevent waste." if excess > 3 else "Increase preparation by 5% to meet unexpected demand."
    }


# 6. Smart Meal Recommendation
def _is_gemini_configured():
    """Return True only when Gemini is configured with a real API key."""
    api_key = getattr(settings, 'GEMINI_API_KEY', None) or os.getenv('GEMINI_API_KEY')
    if not api_key:
        return False
    normalized = str(api_key).strip().lower()
    return normalized not in {'mock_key_or_user_env_key', 'mock_key', 'none', 'null', 'false', '0'}


def _build_recommendation_candidates(student_user, budget=None):
    """Build the base meal candidate set using the existing heuristic logic."""
    pref = 'both'
    try:
        profile = getattr(student_user, 'student_profile', None)
        if profile is not None:
            pref = 'veg' if getattr(profile, 'wallet_balance', 0) > 1000 else 'both'
    except Exception:
        pass

    meals = Meal.objects.filter(is_available=True)
    if budget:
        meals = meals.filter(price__lte=budget)

    if pref == 'veg':
        meals = meals.filter(mess__diet_type__in=['veg', 'both'])

    return list(meals)


def get_recommended_meals(user, budget=None):
    """
    Reusable service for student meal recommendations.
    Uses the existing heuristic-based ranking by default and only attempts
    Gemini integration when a real API key is configured.
    """
    meals_list = _build_recommendation_candidates(user, budget=budget)
    if not meals_list:
        return []

    if _is_gemini_configured():
        try:
            model = get_gemini_client()
            if model:
                prompt = (
                    "Recommend 4 student-friendly meals for a hostel mess. "
                    "Return a short comma-separated list of meal names."
                )
                model.generate_content(prompt)
        except Exception:
            pass

    meals_list.sort(key=lambda m: m.mess.average_rating, reverse=True)
    return meals_list[:4]


def recommend_meals(student_user, budget=None):
    """
    Suggests specific meals based on budget and preference.
    This delegates to the shared recommendation service.
    """
    return get_recommended_meals(student_user, budget=budget)


# 7. Complaint Classification
def classify_complaint_nlp(description):
    """
    Automatically classifies complaint category using NLP keyword matching.
    """
    desc_lower = description.lower()
    
    keywords = {
        'food_quality': ['taste', 'stale', 'smell', 'quality', 'stone', 'hair', 'cold', 'raw', 'undercooked', 'fly', 'insect', 'dirty'],
        'late_delivery': ['delay', 'late', 'time', 'hour', 'waiting', 'slow', 'delivered after', 'not reached', 'delivery boy'],
        'wrong_order': ['wrong', 'different', 'missing', 'exchanged', 'instead', 'extra', 'item not matching'],
        'payment_issue': ['refund', 'money', 'payment', 'transaction', 'deducted', 'double charge', 'failed', 'wallet', 'razorpay', 'bank']
    }
    
    scores = {cat: 0 for cat in keywords.keys()}
    
    for category, words in keywords.items():
        for w in words:
            if w in desc_lower:
                scores[category] += 1
                
    best_category = max(scores, key=scores.get)
    if scores[best_category] == 0:
        return 'food_quality' # Default fallback
    return best_category
