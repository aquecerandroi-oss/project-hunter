"""API process settings, extending :class:`hunter_core.settings.Settings`.

Every field here mirrors a variable in ``.env.example``'s "Ambiente" section.
``ApiSettings`` is what ``create_app`` (``app.py``) and ``main.py`` build the
FastAPI application from; workers keep using the plain core ``Settings``.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import SettingsConfigDict

from hunter_core.settings import Settings


class ApiSettings(Settings):
    """Settings for ``HUNTER_ROLE=api`` — adds HTTP-server-specific fields."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    api_port: int = 8000
    cors_allowed_origins: list[str] = ["http://localhost:3000"]
    rate_limit_per_minute: int = 120
    enable_openapi_docs: bool = False

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_comma_separated(cls, value: object) -> object:
        """Accept ``CORS_ALLOWED_ORIGINS`` as a plain comma-separated string."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def openapi_enabled(self) -> bool:
        """OpenAPI docs (``/docs``, ``/redoc``, ``/openapi.json``) are off in
        production unless explicitly re-enabled with ``ENABLE_OPENAPI_DOCS=true``.
        """
        if self.is_production:
            return self.enable_openapi_docs
        return True


@lru_cache
def get_api_settings() -> ApiSettings:
    """Cached process-wide API settings. Call ``get_api_settings.cache_clear()`` in tests."""
    return ApiSettings()
