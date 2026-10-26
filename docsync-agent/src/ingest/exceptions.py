"""Ingest-specific exceptions."""


class InvalidSignatureError(Exception):
    """Raised when HMAC signature verification fails (maps to HTTP 401)."""


class MissingWebhookHeaderError(Exception):
    """Raised when a required webhook header is missing (maps to HTTP 400)."""


class UnsupportedWebhookEventError(Exception):
    """Raised when webhook event type is not supported (maps to HTTP 202)."""