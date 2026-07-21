import logging
import os
from datetime import datetime
from typing import Iterable, Optional

from django.conf import settings

logger = logging.getLogger(__name__)


def _coerce_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    return default


def is_demo_mode_enabled(service: str, required_values: Optional[Iterable[object]] = None):
    """Return whether a service should use the demo fallback path."""
    setting_value = getattr(settings, 'DEMO_MODE', None)
    if setting_value is None:
        setting_value = os.getenv('DEMO_MODE', 'False')

    has_configured_values = False
    for value in required_values or []:
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() not in {'none', 'null', 'false', '0', 'mock_key_or_user_env_key'}:
            has_configured_values = True
            break

    if _coerce_bool(setting_value, default=False):
        return not has_configured_values

    if not has_configured_values:
        return True
    return False


def log_demo_fallback(service: str, reason: str, fallback: str):
    logger.info(
        'Demo fallback used | service=%s | reason=%s | fallback=%s | timestamp=%s',
        service,
        reason,
        fallback,
        datetime.utcnow().isoformat(),
    )
