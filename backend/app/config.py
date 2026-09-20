from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


_MIN_SECRET_KEY_BYTES = 32
_SESSION_ENCRYPTION_KEY_HEX_LENGTH = 64
_TEMPLATE_SECRET_PREFIXES = ("change-me", "replace-with", "your-")


class Settings(BaseSettings):
    db_path: str = "/app/data/cashflow.db"
    secret_key: str = "dev-secret-key"
    session_encryption_key: str = "0" * 64
    jwt_expire_days: int = 30
    basic_auth_enabled: bool = True
    oidc_enabled: bool = False
    oidc_issuer_url: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = ""
    allowed_origins: str = "http://localhost:3000"
    tz: str = "Europe/Rome"
    development_mode: bool = False
    cookie_secure: bool | None = None

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    def warn_insecure_defaults(self) -> None:
        if self.development_mode:
            return
        self._validate_secret_key()
        self._validate_session_encryption_key()

    def _validate_secret_key(self) -> None:
        value = self.secret_key.strip()
        if self._is_template_secret(value):
            raise ValueError("SECRET_KEY must not use a deployment template placeholder")
        if len(value.encode()) < _MIN_SECRET_KEY_BYTES:
            raise ValueError(
                "SECRET_KEY must contain at least 32 bytes of cryptographically random data"
            )
        if len(set(value)) < 8:
            raise ValueError("SECRET_KEY must not use a low-entropy value")

    def _validate_session_encryption_key(self) -> None:
        value = self.session_encryption_key.strip()
        if self._is_template_secret(value):
            raise ValueError("SESSION_ENCRYPTION_KEY must not use a deployment template placeholder")
        if len(value) != _SESSION_ENCRYPTION_KEY_HEX_LENGTH:
            raise ValueError(
                "SESSION_ENCRYPTION_KEY must be exactly 64 hexadecimal characters (32 bytes)"
            )
        try:
            key = bytes.fromhex(value)
        except ValueError as exc:
            raise ValueError(
                "SESSION_ENCRYPTION_KEY must be exactly 64 hexadecimal characters (32 bytes)"
            ) from exc
        if len(key) != _SESSION_ENCRYPTION_KEY_HEX_LENGTH // 2:
            raise ValueError(
                "SESSION_ENCRYPTION_KEY must be exactly 64 hexadecimal characters (32 bytes)"
            )
        if len(set(value)) < 8:
            raise ValueError("SESSION_ENCRYPTION_KEY must not use a low-entropy value")

    @staticmethod
    def _is_template_secret(value: str) -> bool:
        return not value or value == "dev-secret-key" or value.casefold().startswith(
            _TEMPLATE_SECRET_PREFIXES
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
