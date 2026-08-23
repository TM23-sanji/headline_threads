from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    newsdata_api_key: str = Field(default="", validation_alias=AliasChoices("NEWSDATA_API_KEY", "newsdata_api_key"))
    gnews_api_key: str = Field(default="", validation_alias=AliasChoices("GNEWS_API_KEY", "gnews_api_key"))
    newsapi_api_key: str = Field(default="", validation_alias=AliasChoices("NEWS_API_KEY", "NEWSAPI_API_KEY", "newsapi_api_key"))
    openai_api_key: str = ""

    # Neon Postgres. Empty => fall back to the JSON event store.
    database_url: str = Field(default="", validation_alias=AliasChoices("DATABASE_URL", "database_url"))

    cors_origins: str = "http://localhost:3000"
    events_file: Path = BACKEND_DIR / "data" / "events.json"
    demo_dir: Path = BACKEND_DIR / "data" / "demo"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def has_database(self) -> bool:
        return bool(self.database_url.strip())

    @property
    def configured_providers(self) -> list[str]:
        """Which news providers actually have a key set."""
        pairs = [
            ("newsdata", self.newsdata_api_key),
            ("gnews", self.gnews_api_key),
            ("newsapi", self.newsapi_api_key),
        ]
        return [name for name, key in pairs if key.strip()]


settings = Settings()
