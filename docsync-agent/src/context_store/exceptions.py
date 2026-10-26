"""ContextStore-specific exceptions."""


class ContextStoreError(Exception):
    """Base exception for all ContextStore failures."""


class DatabaseNotInitializedError(ContextStoreError):
    """Raised when a store method is called before ``initialize()``."""