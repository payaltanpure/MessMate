import logging
import os

from django.conf import settings
from django.core.mail import send_mail

from core.integration_fallbacks import is_demo_mode_enabled, log_demo_fallback

logger = logging.getLogger(__name__)


def _smtp_settings():
    return {
        'EMAIL_HOST': getattr(settings, 'EMAIL_HOST', os.getenv('EMAIL_HOST', '')).strip(),
        'EMAIL_PORT': str(getattr(settings, 'EMAIL_PORT', os.getenv('EMAIL_PORT', ''))).strip(),
        'EMAIL_HOST_USER': getattr(settings, 'EMAIL_HOST_USER', os.getenv('EMAIL_HOST_USER', '')).strip(),
        'EMAIL_HOST_PASSWORD': getattr(settings, 'EMAIL_HOST_PASSWORD', os.getenv('EMAIL_HOST_PASSWORD', '')).strip(),
        'DEFAULT_FROM_EMAIL': getattr(settings, 'DEFAULT_FROM_EMAIL', os.getenv('DEFAULT_FROM_EMAIL', '')) or 'noreply@messmate.local',
    }


def _smtp_configured():
    smtp = _smtp_settings()
    return bool(smtp['EMAIL_HOST'] and smtp['EMAIL_PORT'] and smtp['EMAIL_HOST_USER'] and smtp['EMAIL_HOST_PASSWORD'])


def send_email_message(subject, message, recipient_list, html_message=None, category='general'):
    """Send an email when SMTP is configured, otherwise use the demo fallback."""
    recipients = [recipient for recipient in recipient_list if recipient]
    if not recipients:
        logger.info('Email skipped for %s: no recipient addresses', category)
        return False

    smtp = _smtp_settings()
    if not _smtp_configured() or is_demo_mode_enabled('email', [smtp['EMAIL_HOST'], smtp['EMAIL_PORT'], smtp['EMAIL_HOST_USER'], smtp['EMAIL_HOST_PASSWORD']]):
        log_demo_fallback('email', 'SMTP credentials missing or demo mode enabled', 'store email content locally')
        logger.info('Email sent successfully (Demo Mode) for %s to %s', category, ', '.join(recipients))
        return True

    try:
        send_mail(
            subject,
            message,
            smtp['DEFAULT_FROM_EMAIL'],
            recipients,
            html_message=html_message,
            fail_silently=False,
        )
    except Exception as exc:
        logger.exception('Email sending failed for %s: %s', category, exc)
        return False

    logger.info('Email sent for %s to %s', category, ', '.join(recipients))
    return True


def send_registration_email(user_type, user_name, email, verification_url):
    subject = 'Welcome to MessMate'
    message = (
        f"Hi {user_name},\n\n"
        f"Your {user_type} account has been created successfully.\n"
        f"Verify your email here: {verification_url}\n"
    )
    return send_email_message(subject, message, [email], html_message=message.replace('\n', '<br>'), category='registration')


def send_order_confirmation_email(user_name, email, order_id, amount):
    subject = 'Order confirmed'
    message = (
        f"Hi {user_name},\n\n"
        f"Your order #{order_id} has been confirmed.\n"
        f"Amount paid: Rs.{amount}\n"
    )
    return send_email_message(subject, message, [email], html_message=message.replace('\n', '<br>'), category='order_confirmation')


def send_subscription_confirmation_email(user_name, email, mess_name, plan_type):
    subject = 'Subscription confirmed'
    message = (
        f"Hi {user_name},\n\n"
        f"Your subscription to {mess_name} ({plan_type}) has been activated.\n"
    )
    return send_email_message(subject, message, [email], html_message=message.replace('\n', '<br>'), category='subscription_confirmation')


def send_complaint_resolution_email(user_name, email, complaint_id, response):
    subject = 'Complaint update'
    message = (
        f"Hi {user_name},\n\n"
        f"Your complaint #{complaint_id} has been resolved.\n"
        f"Response: {response}\n"
    )
    return send_email_message(subject, message, [email], html_message=message.replace('\n', '<br>'), category='complaint_update')


def send_password_reset_email(user_name, email, reset_url):
    subject = 'Password reset request'
    message = (
        f"Hi {user_name},\n\n"
        f"Use the following link to reset your password: {reset_url}\n"
    )
    return send_email_message(subject, message, [email], html_message=message.replace('\n', '<br>'), category='password_reset')


# Reusable notification helpers for student/vendor/admin flows.
def send_vendor_notification(user_name, email, subject, message, category='vendor_notification'):
    return send_email_message(subject, message, [email], html_message=message.replace('\n', '<br>'), category=category)


def send_admin_notification(email, subject, message, category='admin_notification'):
    return send_email_message(subject, message, [email], html_message=message.replace('\n', '<br>'), category=category)


def send_daily_report_email(email, report_text, category='daily_report'):
    subject = 'SMARTMESS AI Daily Report'
    return send_email_message(subject, report_text, [email], html_message=report_text.replace('\n', '<br>'), category=category)


def send_critical_alert_email(email, message, category='critical_alert'):
    subject = 'SMARTMESS AI Critical Alert'
    return send_email_message(subject, message, [email], html_message=message.replace('\n', '<br>'), category=category)
