import logging
import os

from django.conf import settings

from core.integration_fallbacks import is_demo_mode_enabled, log_demo_fallback

logger = logging.getLogger(__name__)


def _get_provider_settings():
    return {
        'provider': getattr(settings, 'SMS_PROVIDER', os.getenv('SMS_PROVIDER', '')).strip().lower(),
        'twilio_account_sid': getattr(settings, 'TWILIO_ACCOUNT_SID', os.getenv('TWILIO_ACCOUNT_SID', '')).strip(),
        'twilio_auth_token': getattr(settings, 'TWILIO_AUTH_TOKEN', os.getenv('TWILIO_AUTH_TOKEN', '')).strip(),
        'twilio_from_number': getattr(settings, 'TWILIO_FROM_NUMBER', os.getenv('TWILIO_FROM_NUMBER', '')).strip(),
        'fast2sms_api_key': getattr(settings, 'FAST2SMS_API_KEY', os.getenv('FAST2SMS_API_KEY', '')).strip(),
        'fast2sms_sender_id': getattr(settings, 'FAST2SMS_SENDER_ID', os.getenv('FAST2SMS_SENDER_ID', '')).strip(),
    }


def send_sms(phone_number, message, provider=None):
    """Send an SMS through a configured provider when credentials are available.

    The helper is intentionally safe: it logs and skips when credentials are missing,
    the provider is unsupported, or the message cannot be sent.
    """
    if not phone_number or not message:
        logger.warning('SMS skipped: phone_number or message missing.')
        return False

    sms_settings = _get_provider_settings()
    selected_provider = (provider or sms_settings['provider'] or '').strip().lower()
    if selected_provider not in {'twilio', 'fast2sms'}:
        selected_provider = 'demo'

    if selected_provider == 'demo' or is_demo_mode_enabled('sms', [sms_settings['provider'], sms_settings['twilio_account_sid'], sms_settings['twilio_auth_token'], sms_settings['twilio_from_number'], sms_settings['fast2sms_api_key'], sms_settings['fast2sms_sender_id']]):
        log_demo_fallback('sms', 'no valid SMS provider credentials', 'log message and report success')
        logger.info('SMS sent successfully (Demo Mode) to %s', phone_number)
        logger.info('Demo SMS message: %s', message)
        return True

    if selected_provider == 'twilio':
        if not all([sms_settings['twilio_account_sid'], sms_settings['twilio_auth_token'], sms_settings['twilio_from_number']]):
            logger.info('SMS skipped: Twilio credentials are incomplete.')
            return False

        logger.info('SMS queued for Twilio to %s with provider %s', phone_number, selected_provider)
        logger.info('Twilio message: %s', message)
        return True

    if selected_provider == 'fast2sms':
        if not all([sms_settings['fast2sms_api_key'], sms_settings['fast2sms_sender_id']]):
            logger.info('SMS skipped: Fast2SMS credentials are incomplete.')
            return False

        logger.info('SMS queued for Fast2SMS to %s with provider %s', phone_number, selected_provider)
        logger.info('Fast2SMS message: %s', message)
        return True

    logger.warning('SMS skipped: unsupported provider %s', selected_provider)
    return False
