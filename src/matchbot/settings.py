from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM
    llm_provider: str = Field(default="anthropic", description="anthropic | openai")
    anthropic_api_key: str = Field(default="")
    anthropic_model: str = Field(default="claude-haiku-4-5")
    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4o-mini")
    openai_service_tier: str | None = Field(
        default=None,
        description="OpenAI service tier: 'priority', 'flex', or None for default",
    )
    llm_extraction_confidence_threshold: float = Field(default=0.7)

    # Matching
    matching_min_score: float = Field(default=0.3)
    matching_llm_triage_band_low: float = Field(default=0.3)
    matching_llm_triage_band_high: float = Field(default=0.55)

    # Reddit
    reddit_enabled: bool = Field(default=True)
    reddit_client_id: str = Field(default="")
    reddit_client_secret: str = Field(default="")
    reddit_user_agent: str = Field(default="matchbot/0.1")
    reddit_username: str = Field(default="")
    reddit_password: str = Field(default="")
    reddit_json_enabled: bool = Field(default=True)
    reddit_json_poll_interval_seconds: int = Field(default=300)
    reddit_json_fetch_limit: int = Field(default=100)
    reddit_json_user_agent: str = Field(default="matchbot/0.1 (json-poller)")

    # Discord
    discord_enabled: bool = Field(default=True)
    discord_bot_token: str = Field(default="")
    discord_moderator_channel_id: str = Field(default="")

    # Facebook
    facebook_enabled: bool = Field(default=True)
    facebook_app_id: str = Field(default="")
    facebook_app_secret: str = Field(default="")
    facebook_page_access_token: str = Field(default="")
    facebook_verify_token: str = Field(default="")

    # Server
    server_host: str = Field(default="0.0.0.0")
    server_port: int = Field(default=8080)
    verbose: bool = Field(default=False, description="Enable verbose logging/debug output")

    # Storage
    database_backend: Literal["sqlite", "neon"] = Field(
        default="sqlite",
        description="Database backend to use: 'sqlite' or 'neon'.",
    )
    db_path: str = Field(default="matchbot.db")
    neon_database_url: str = Field(
        default="",
        description=(
            "Optional Neon Postgres URL. Example: "
            "postgresql://user:pass@host.neon.tech:5432/dbname?sslmode=require"
        ),
    )
    report_output_dir: str = Field(default="./reports")

    @property
    def reddit_configured(self) -> bool:
        return bool(
            self.reddit_client_id
            and self.reddit_client_secret
            and self.reddit_username
            and self.reddit_password
        )

    @property
    def discord_configured(self) -> bool:
        return bool(self.discord_bot_token)

    @property
    def facebook_configured(self) -> bool:
        return bool(
            self.facebook_app_id
            and self.facebook_app_secret
            and self.facebook_page_access_token
            and self.facebook_verify_token
        )

    # Moderator
    moderator_name: str = Field(default="Matchbot Moderator")
    mod_password: str = Field(default="", description="Password for /api/mod auth")
    mod_secret_key: str = Field(default="", description="HMAC secret for mod_session cookie")

    # WWW Guide enrichment
    www_guide_url: str = Field(
        default="",
        description="URL to Burning Man WWW Guide camp JSON endpoint. Leave blank to disable.",
    )
    www_guide_year: int | None = Field(
        default=None,
        description="Burn year to tag guide-enriched data. Defaults to current year if blank.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
