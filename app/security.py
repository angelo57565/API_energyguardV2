import secrets

from fastapi import Header, HTTPException, status

from .config import get_settings


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Se API_KEY estiver definida no .env, exige o header X-API-Key."""
    expected = get_settings().api_key
    if not expected:
        return
    if not secrets.compare_digest(x_api_key or "", expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key inválida ou ausente")
