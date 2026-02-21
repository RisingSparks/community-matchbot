from functools import lru_cache

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
    openai_service_tier: str | None = Field(default=None, description="OpenAI service tier: 'priority', 'flex', or None for default")
    llm_extraction_confidence_threshold: float = Field(default=0.7)

    # Matching
    matching_min_score: float = Field(default=0.3)
    matching_llm_triage_band_low: float = Field(default=0.3)
    matching_llm_triage_band_high: float = Field(default=0.55)

    # Reddit
    reddit_client_id: str = Field(default="")
    reddit_client_secret: str = Field(default="")
    reddit_user_agent: str = Field(default="matchbot/0.1")
    reddit_username: str = Field(default="")
    reddit_password: str = Field(default="")

    # Discord
    discord_bot_token: str = Field(default="")
    discord_moderator_channel_id: str = Field(default="")

    # Facebook
    facebook_app_id: str = Field(default="")
    facebook_app_secret: str = Field(default="")
    facebook_page_access_token: str = Field(default="")
    facebook_verify_token: str = Field(default="")

    # Server
    server_host: str = Field(default="0.0.0.0")
    server_port: int = Field(default=8080)
    verbose: bool = Field(default=False, description="Enable verbose logging/debug output")

    # Storage
    db_path: str = Field(default="matchbot.db")
    report_output_dir: str = Field(default="./reports")

    # Moderator
    moderator_name: str = Field(default="Matchbot Moderator")

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
