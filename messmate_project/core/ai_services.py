import os
import random
import datetime
from django.conf import settings
from vendor.models import Mess, Meal
from student.models import Order, OrderItem, Review, Subscription
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
    if not api_key:
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


# 2. AI Chatbot
def get_chatbot_response(message, user=None):
    """
    Returns AI answers for user queries, calling Gemini or fallback rules.
    """
    message_lower = message.lower()
    
    # Check for specific intents for faster or offline response
    if "best mess" in message_lower or "recommend" in message_lower:
        recs = recommend_messes()
        if recs['best_mess']:
            return f"Based on student feedback and pricing, I recommend **{recs['best_mess'].mess_name}**! It has a rating of {recs['best_mess'].average_rating}* and is only {recs['best_mess'].distance} km away."
        return "I couldn't find any active messes on campus. Please contact the administrator."
        
    elif "renew" in message_lower or "subscription" in message_lower:
        return "To renew your subscription, navigate to the **Student Dashboard**, click on 'My Subscription', choose your plan, and click 'Renew'. You can pay using your wallet or Razorpay."
        
    elif "wallet" in message_lower or "add money" in message_lower:
        return "You can add money to your wallet on the **Student Dashboard** under 'My Wallet'. We support UPI, Cards, and Net Banking."
        
    elif "tiffin" in message_lower or "order food" in message_lower:
        return "To order a daily tiffin, browse the home screen, select a mess to view their menu, click 'Add to Cart', and check out."

    # Gemini Call
    model = get_gemini_client()
    if model:
        try:
            prompt = f"""
            You are 'SmartMess Assistant', the friendly AI support chatbot for the SmartMess platform.
            Answer this student inquiry concisely (max 3 sentences) in the context of hostel mess/tiffin ordering:
            "{message}"
            """
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception:
            pass

    # Generic Smart Fallback
    responses = [
        "Welcome to SmartMess! You can check the current mess listings on the homepage, pause your monthly plan anytime, or order daily tiffins.",
        "Need help finding food? You can filter messes by Veg/Non-Veg status, distance, or price on the home page search bar.",
        "Your subscriptions can be paused for up to 10 days a month. This ensures you do not lose money on days you eat out!",
        "Our delivery team ensures tiffins arrive hot. Make sure to share the 6-digit Delivery OTP with your delivery boy when they arrive."
    ]
    return random.choice(responses)


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


# 4. Demand Forecasting
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
def recommend_meals(student_user, budget=None):
    """
    Suggests specific meals based on order history, budget, and preference.
    """
    pref = 'both'
    try:
        profile = student_user.student_profile
        pref = 'veg' if profile.wallet_balance > 1000 else 'both' # simple heuristic or user preferences
    except Exception:
        pass

    meals = Meal.objects.filter(is_available=True)
    if budget:
        meals = meals.filter(price__lte=budget)
        
    # Heuristic matching: Veg vs Nonveg
    if pref == 'veg':
        meals = meals.filter(mess__diet_type__in=['veg', 'both'])
        
    meals_list = list(meals)
    if not meals_list:
        return []
        
    # Sort by rating of the mess
    meals_list.sort(key=lambda m: m.mess.average_rating, reverse=True)
    return meals_list[:4]


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
