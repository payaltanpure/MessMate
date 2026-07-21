import json
import logging
import os

from django.conf import settings

from core.integration_fallbacks import is_demo_mode_enabled, log_demo_fallback
from student.models import Notification

logger = logging.getLogger(__name__)


def save_fcm_token(user, token):
    """Persist an FCM token on the user model when a token is provided."""
    if not user or not token:
        return False

    normalized = str(token).strip()
    if not normalized:
        return False

    user.fcm_token = normalized
    user.save(update_fields=['fcm_token'])
    logger.info('Saved FCM token for user %s', getattr(user, 'username', user.id))
    return True


def send_push_notification(user, title, body, data=None):
    """Send a Firebase push notification when credentials and a token are available."""
    if not user or not title or not body:
        return False

    firebase_project_id = getattr(settings, 'FIREBASE_PROJECT_ID', os.getenv('FIREBASE_PROJECT_ID', '')).strip()
    firebase_credentials_json = getattr(settings, 'FIREBASE_CREDENTIALS_JSON', os.getenv('FIREBASE_CREDENTIALS_JSON', '')).strip()
    should_use_demo = not firebase_project_id or not firebase_credentials_json or is_demo_mode_enabled('push_notification', [firebase_project_id, firebase_credentials_json])
    if not should_use_demo:
        token = getattr(user, 'fcm_token', '') or ''
        if not token:
            logger.info('Push notification skipped: no FCM token for user %s', getattr(user, 'username', user.id))
            return False

    if should_use_demo:
        log_demo_fallback('push_notification', 'Firebase credentials missing or demo mode enabled', 'store notification locally and display in-app')
        Notification.objects.create(
            user=user,
            title=title,
            message=body,
            notification_type='push',
            status='sent',
        )
        logger.info('Push Notification Delivered (Demo Mode) for user %s: %s - %s', getattr(user, 'username', user.id), title, body)
        return True

    try:
        json.loads(firebase_credentials_json)
    except Exception:
        logger.info('Push notification skipped: Firebase credentials JSON is invalid.')
        return False

    logger.info('Push notification queued for user %s: %s - %s', getattr(user, 'username', user.id), title, body)
    if data:
        logger.info('Push payload data: %s', data)
    return True
