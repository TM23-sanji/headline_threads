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
    # Regex applied in addition to the exact origins list. Needed because
    # Vercel preview deploys use a per-commit hostname
    # (e.g. https://headline-threads-git-<branch>-<team>.vercel.app).
    cors_origin_regex: str = ""

    # Rotate this before deploying. Guards POST /api/admin/ingest so a
    # scheduled job (GitHub Actions) can trigger ingest without opening the
    # endpoint to the public.
    ingest_secret: str = ""

    # Retained only for scripts/fetch_demo_data.py fixture output; runtime
    # code does not touch the filesystem.
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
