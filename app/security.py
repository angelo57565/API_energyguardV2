import secrets

from fastapi import Header, HTTPException, status

from .config import get_settings


def _check_key(provided: str | None, expected: str) -> None:
    if not expected:
        return
    if not secrets.compare_digest((provided or "").encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key inválida ou ausente")


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    _check_key(x_api_key, get_settings().api_key)


def require_ingest_key(x_api_key: str | None = Header(default=None)) -> None:
    settings = get_settings()
    _check_key(x_api_key, settings.ingest_api_key or settings.api_key)
