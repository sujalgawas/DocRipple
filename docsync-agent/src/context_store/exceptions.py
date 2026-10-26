"""ContextStore-specific exceptions."""


class StorageError(RuntimeError):
    """Generic storage operation failure."""


class EdgeNotFoundError(KeyError):
    """Requested code_doc_edge does not exist."""