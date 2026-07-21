import os
import random
from datetime import datetime

import requests
from django.conf import settings

from core.integration_fallbacks import is_demo_mode_enabled, log_demo_fallback


def _get_openweather_api_key():
    return (getattr(settings, 'OPENWEATHER_API_KEY', '') or os.getenv('OPENWEATHER_API_KEY', '') or '').strip()


def _weather_unavailable(city, message='Weather unavailable'):
    return {
        'available': False,
        'message': message,
        'city': city,
    }


def _build_demo_weather(city):
    season = 'summer' if datetime.now().month in {3, 4, 5, 6, 7, 8} else 'winter'
    if season == 'summer':
        temperature = random.randint(28, 35)
        condition = 'Sunny'
        humidity = random.randint(40, 65)
        rain_probability = random.randint(5, 20)
    else:
        temperature = random.randint(16, 24)
        condition = 'Cloudy'
        humidity = random.randint(60, 85)
        rain_probability = random.randint(35, 70)
    return {
        'available': True,
        'city': city,
        'temperature': temperature,
        'description': f'{condition} with a comfortable breeze',
        'icon': '01d',
        'humidity': humidity,
        'rain_probability': rain_probability,
        'message': f'Demo weather for {city}: {condition}, {temperature}°C, humidity {humidity}%, rain probability {rain_probability}%.',
        'demo': True,
    }


def get_weather(city):
    """Return a simple weather payload for the provided city.

    The service uses OpenWeather if an API key is configured, otherwise it
    returns a safe fallback payload so the UI can show a friendly message.
    """
    api_key = _get_openweather_api_key()
    if not api_key or is_demo_mode_enabled('weather', [api_key]):
        log_demo_fallback('weather', 'OpenWeather API key missing', 'generate demo weather data')
        return _build_demo_weather(city)

    try:
        response = requests.get(
            'https://api.openweathermap.org/data/2.5/weather',
            params={'q': city, 'appid': api_key, 'units': 'metric'},
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        weather = data.get('weather', [{}])[0]
        main = data.get('main', {})
        description = weather.get('description', 'No data').capitalize()
        return {
            'available': True,
            'city': data.get('name', city),
            'temperature': round(main.get('temp', 0)),
            'description': description,
            'icon': weather.get('icon', ''),
        }
    except Exception:
        return _weather_unavailable(city)


def get_weather_recommendations(city, meals=None):
    """Return simple weather-aware meal suggestions while staying safe without an API key."""
    weather = get_weather(city)
    if not weather.get('available', False):
        return {
            'available': False,
            'message': weather.get('message', 'Weather unavailable'),
            'city': city,
            'items': [],
        }

    meal_names = []
    for meal in meals or []:
        if hasattr(meal, 'name'):
            meal_names.append(meal.name)
        else:
            meal_names.append(str(meal))

    meal_names = [meal for meal in meal_names if meal]
    if not meal_names:
        meal_names = ['Soup', 'Biryani', 'Salad', 'Paratha', 'Rice Bowl']

    if weather.get('demo'):
        preferred = [meal for meal in meal_names if any(keyword in meal.lower() for keyword in ['soup', 'biryani', 'paratha', 'khichdi', 'salad', 'rice', 'dosa', 'idli'])][:2] or meal_names[:2]
        return {
            'available': True,
            'city': weather.get('city', city),
            'temperature': weather.get('temperature', 0),
            'description': weather.get('description', ''),
            'message': f"Demo weather for {city}: {weather.get('description', '')} with {weather.get('temperature', 0)}°C. Try {', '.join(preferred)} today.",
            'items': preferred[:2],
        }

    description = (weather.get('description') or '').lower()
    temperature = weather.get('temperature', 0)

    if temperature >= 30 or 'clear' in description:
        preferred = [
            meal for meal in meal_names
            if any(keyword in meal.lower() for keyword in ['salad', 'juice', 'curd', 'fruit', 'rice', 'dosa', 'idli'])
        ] or meal_names[:2]
    elif temperature <= 18 or any(keyword in description for keyword in ['rain', 'drizzle', 'mist', 'cloud']):
        preferred = [
            meal for meal in meal_names
            if any(keyword in meal.lower() for keyword in ['soup', 'biryani', 'paratha', 'khichdi', 'curry', 'pasta'])
        ] or meal_names[:2]
    else:
        preferred = meal_names[:2]

    return {
        'available': True,
        'city': weather.get('city', city),
        'temperature': weather.get('temperature', 0),
        'description': weather.get('description', ''),
        'message': f"{weather.get('description', '')} with {weather.get('temperature', 0)}°C. Try {', '.join(preferred[:2])} today.",
        'items': preferred[:2],
    }


def get_weather_impact(city):
    """Return a simple demand-impact note based on weather conditions."""
    weather = get_weather(city)
    if not weather.get('available', False):
        return {
            'available': False,
            'message': weather.get('message', 'Weather unavailable'),
            'city': city,
            'impact': 'unknown',
        }

    if weather.get('demo'):
        return {
            'available': True,
            'city': weather.get('city', city),
            'temperature': weather.get('temperature', 0),
            'description': weather.get('description', ''),
            'message': f"Demo weather impact for {city}: {weather.get('description', '')} with {weather.get('temperature', 0)}°C and moderate demand.",
            'impact': 'steady',
        }

    description = (weather.get('description') or '').lower()
    temperature = weather.get('temperature', 0)

    if temperature >= 30:
        message = 'High heat is likely to increase demand for lighter meals and cold beverages.'
        impact = 'heat'
    elif temperature <= 18 or any(keyword in description for keyword in ['rain', 'drizzle', 'mist', 'cloud']):
        message = 'Cooler or rainy weather often lifts demand for comfort food and warm meals.'
        impact = 'cool'
    else:
        message = 'Mild weather should keep demand steady today.'
        impact = 'steady'

    return {
        'available': True,
        'city': weather.get('city', city),
        'temperature': temperature,
        'description': weather.get('description', ''),
        'message': message,
        'impact': impact,
    }
