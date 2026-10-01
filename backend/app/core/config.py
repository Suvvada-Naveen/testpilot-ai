from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr


class Settings(BaseSettings):
    app_env: str = "development"
    frontend_url: str = "http://localhost:5173"
    browser_headless: bool = True
    browser_timeout: int = 30000
    max_page_text_length: int = 20000
    max_console_messages: int = 100
    allow_local_urls: bool = False
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.6-mini"
    openai_timeout_seconds: float = 60
    max_ai_page_text: int = 12000
    max_ai_links: int = 100
    max_ai_elements: int = 200
    max_ai_test_cases: int = 30
    action_timeout: int = 10000
    navigation_timeout: int = 30000
    max_actions_per_test: int = 30
    max_test_cases_per_execution: int = 10
    test_credential_username: str | None = None
    test_credential_password: SecretStr | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )