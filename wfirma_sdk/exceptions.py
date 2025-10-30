from __future__ import annotations


class WFirmaError(Exception):
    """Base error for the wFirma SDK."""


class WFirmaAuthError(WFirmaError):
    """Authentication/authorization problems."""


class WFirmaAPIError(WFirmaError):
    """Non-2xx response or API-level ERROR from wFirma API."""

    def __init__(self, status_code: int | None, message: str, payload=None):
        super().__init__(
            f"[{status_code if status_code is not None else '-'}] {message}"
        )
        self.status_code = status_code
        self.payload = payload
