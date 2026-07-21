from django.conf import settings


def ga_measurement_id(request):
    return {
        'ga_measurement_id': getattr(settings, 'GA_MEASUREMENT_ID', '').strip(),
    }
