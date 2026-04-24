from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str
    database_url: str

    threexui_base_url: str
    threexui_subscription_base_url: str = ""
    threexui_username: str
    threexui_password: str
    threexui_inbound_id: int

    admin_telegram_ids_raw: str = ""
    admin_receipts_chat_id: str = ""
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    threexui_verify_ssl: bool = True
    bot_instance_lock_id: int = 424242
    allow_test_payments: bool = False
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    yookassa_return_url: str = ""
    yookassa_receipts_enabled: bool = False
    yookassa_receipt_vat_code: int = 1
    yookassa_receipt_payment_subject: str = "service"
    yookassa_receipt_payment_mode: str = "full_payment"
    internal_api_token: str = ""
    instruction_url: str = "https://t.me/Norticboost/3"
    support_url: str = "https://t.me/nortic_team"
    privacy_policy_url: str = ""
    terms_of_service_url: str = ""
    legal_version: str = "2026-04-06"
    subscription_profile_title: str = "Nortic"
    subscription_update_interval_hours: int = 3
    subscription_profile_url: str = ""
    subscription_announce: str = ""
    happ_routing_rule_url: str = ""

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


def is_yookassa_receipts_enabled() -> bool:
    return is_yookassa_configured() and settings.yookassa_receipts_enabled


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


def get_admin_telegram_ids() -> set[int]:
    return parse_admin_telegram_ids(settings.admin_telegram_ids_raw)


def get_admin_receipts_chat_id() -> int | None:
    raw_value = settings.admin_receipts_chat_id.strip()
    if not raw_value:
        return None
    return int(raw_value)
