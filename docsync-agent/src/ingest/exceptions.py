"""Ingest-specific exceptions."""


class InvalidSignatureError(ValueError):
    """HMAC verification failed — request is not from GitHub."""


class DuplicateDeliveryError(ValueError):
    """Delivery ID already processed — idempotency guard."""