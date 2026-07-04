from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from vendor.models import Mess
from .ai_services import get_chatbot_response, recommend_messes
import json

def home(request):
    """
    Main Landing Page listing all active messes with advanced filters.
    """
    query = request.GET.get('q', '')
    diet_type = request.GET.get('diet_type', '')
    max_price = request.GET.get('max_price', '')
    max_distance = request.GET.get('max_distance', '')
    min_rating = request.GET.get('min_rating', '')

    messes = Mess.objects.filter(is_active=True)

    if query:
        messes = messes.filter(mess_name__icontains=query) | messes.filter(description__icontains=query)
    
    if diet_type and diet_type != 'all':
        if diet_type == 'veg':
            messes = messes.filter(diet_type__in=['veg', 'both'])
        elif diet_type == 'non-veg':
            messes = messes.filter(diet_type__in=['non-veg', 'both'])

    if max_price:
        try:
            messes = messes.filter(monthly_price_both__lte=float(max_price)) | messes.filter(daily_tiffin_price__lte=float(max_price)/30)
        except ValueError:
            pass

    if max_distance:
        try:
            messes = messes.filter(distance__lte=float(max_distance))
        except ValueError:
            pass

    if min_rating:
        try:
            messes = messes.filter(average_rating__gte=float(min_rating))
        except ValueError:
            pass

    # AI Recommendation Engine integration on home page
    ai_recs = recommend_messes(
        student_pref=diet_type if diet_type in ['veg', 'non-veg'] else 'both',
        budget=float(max_price) if max_price else None
    )

    context = {
        'messes': messes,
        'ai_recs': ai_recs,
        'query': query,
        'diet_type': diet_type,
        'max_price': max_price,
        'max_distance': max_distance,
        'min_rating': min_rating
    }
    return render(request, 'core/home.html', context)


@csrf_exempt
def chatbot_api(request):
    """
    Chatbot API that processes user messages and returns AI-generated responses.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            user_message = data.get('message', '')
            if not user_message:
                return JsonResponse({'error': 'Empty message'}, status=400)
            
            response_text = get_chatbot_response(user_message, request.user if request.user.is_authenticated else None)
            return JsonResponse({'reply': response_text})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
            
    return JsonResponse({'error': 'POST method required'}, status=405)


def recommendation_api(request):
    """
    JSON API for recommendations.
    """
    diet = request.GET.get('diet', 'both')
    budget = request.GET.get('budget', None)
    if budget:
        try:
            budget = float(budget)
        except ValueError:
            budget = None

    recs = recommend_messes(student_pref=diet, budget=budget)
    serialized = {
        'best_mess': {
            'id': recs['best_mess'].id,
            'name': recs['best_mess'].mess_name,
            'rating': float(recs['best_mess'].average_rating),
            'price': float(recs['best_mess'].monthly_price_both)
        } if recs['best_mess'] else None,
        'best_value': {
            'id': recs['best_value'].id,
            'name': recs['best_value'].mess_name,
            'rating': float(recs['best_value'].average_rating),
            'price': float(recs['best_value'].monthly_price_both)
        } if recs['best_value'] else None,
        'most_popular': {
            'id': recs['most_popular'].id,
            'name': recs['most_popular'].mess_name,
            'rating': float(recs['most_popular'].average_rating),
            'price': float(recs['most_popular'].monthly_price_both)
        } if recs['most_popular'] else None
    }
    return JsonResponse(serialized)