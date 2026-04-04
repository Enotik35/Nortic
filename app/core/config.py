from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str
    database_url: str

    threexui_base_url: str
    threexui_username: str
    threexui_password: str
    threexui_inbound_id: int

    admin_telegram_ids_raw: str = ""
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    threexui_verify_ssl: bool = True
    bot_instance_lock_id: int = 424242
    allow_test_payments: bool = False
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    yookassa_return_url: str = ""
    internal_api_token: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


def is_yookassa_configured() -> bool:
    return bool(
        settings.yookassa_shop_id.strip()
        and settings.yookassa_secret_key.strip()
        and settings.yookassa_return_url.strip()
    )


def is_internal_api_token_configured() -> bool:
    return bool(settings.internal_api_token.strip())


def parse_admin_telegram_ids(raw_value: str) -> set[int]:
    result: set[int] = set()
    for chunk in raw_value.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        result.add(int(chunk))
    return result
