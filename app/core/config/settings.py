from pathlib import Path

from pydantic import AliasChoices
from pydantic import Field
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/ceaser",
        validation_alias=AliasChoices("DATABASE_URL", "database_url"),
    )
    supabase_url: str | None = Field(default=None, validation_alias=AliasChoices("SUPABASE_URL", "supabase_url"))
    supabase_anon_key: str | None = Field(default=None, validation_alias=AliasChoices("SUPABASE_ANON_KEY", "supabase_anon_key"))
    supabase_service_role_key: str | None = Field(default=None, validation_alias=AliasChoices("SUPABASE_SERVICE_ROLE_KEY", "supabase_service_role_key"))
    jwt_secret: str | None = Field(default=None, validation_alias=AliasChoices("JWT_SECRET", "jwt_secret"))
    encryption_master_key: str | None = Field(default=None, validation_alias=AliasChoices("ENCRYPTION_MASTER_KEY", "encryption_master_key"))
    cors_origins_raw: str = Field(default="http://localhost:3000,http://localhost:3001", alias="CORS_ORIGINS")
    dev_auth_bypass: bool = Field(default=False, alias="DEV_AUTH_BYPASS")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    llm_provider: str = Field(default="gemini", alias="LLM_PROVIDER")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    gemini_temperature: float = Field(default=0.4, alias="GEMINI_TEMPERATURE")
    gemini_max_tokens: int = Field(default=1200, alias="GEMINI_MAX_TOKENS")
    stt_provider: str = Field(default="deepgram", alias="STT_PROVIDER")
    deepgram_api_key: str | None = Field(default=None, alias="DEEPGRAM_API_KEY")
    tts_provider: str = Field(default="elevenlabs", alias="TTS_PROVIDER")
    elevenlabs_api_key: str | None = Field(default=None, alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str | None = Field(default=None, alias="ELEVENLABS_VOICE_ID")
    voice_default_language: str = Field(default="en", alias="VOICE_DEFAULT_LANGUAGE")
    supabase_storage_bucket: str = Field(default="ceaser-files", alias="SUPABASE_STORAGE_BUCKET")
    local_upload_dir: str = Field(default="storage/uploads", alias="LOCAL_UPLOAD_DIR")
    automation_worker_enabled: bool = Field(default=True, alias="AUTOMATION_WORKER_ENABLED")
    automation_worker_interval_seconds: int = Field(default=60, alias="AUTOMATION_WORKER_INTERVAL_SECONDS")
    automation_worker_batch_size: int = Field(default=10, alias="AUTOMATION_WORKER_BATCH_SIZE")
    automation_worker_max_retries: int = Field(default=3, alias="AUTOMATION_WORKER_MAX_RETRIES")
    automation_worker_retry_delay_seconds: int = Field(default=600, alias="AUTOMATION_WORKER_RETRY_DELAY_SECONDS")
    google_client_id: str | None = Field(default=None, alias="GOOGLE_CLIENT_ID")
    google_client_secret: str | None = Field(default=None, alias="GOOGLE_CLIENT_SECRET")
    google_oauth_redirect_uri: str = Field(default="http://localhost:8000/integrations/google-calendar/callback", alias="GOOGLE_OAUTH_REDIRECT_URI")
    google_redirect_base_url: str = Field(default="http://localhost:8000", alias="GOOGLE_REDIRECT_BASE_URL")
    frontend_app_url: str = Field(default="http://localhost:3000", alias="FRONTEND_APP_URL")
    google_calendar_oauth_redirect_uri: str = Field(default="http://localhost:8000/integrations/google-calendar/callback", alias="GOOGLE_CALENDAR_OAUTH_REDIRECT_URI")
    google_gmail_oauth_redirect_uri: str = Field(default="http://localhost:8000/integrations/gmail/callback", alias="GOOGLE_GMAIL_OAUTH_REDIRECT_URI")
    google_drive_oauth_redirect_uri: str = Field(default="http://localhost:8000/integrations/google-drive/callback", alias="GOOGLE_DRIVE_OAUTH_REDIRECT_URI")
    google_tasks_oauth_redirect_uri: str = Field(default="http://localhost:8000/integrations/google-tasks/callback", alias="GOOGLE_TASKS_OAUTH_REDIRECT_URI")
    google_classroom_oauth_redirect_uri: str = Field(default="http://localhost:8000/integrations/google-classroom/callback", alias="GOOGLE_CLASSROOM_OAUTH_REDIRECT_URI")
    youtube_api_key: str | None = Field(default=None, alias="YOUTUBE_API_KEY")
    notion_client_id: str | None = Field(default=None, alias="NOTION_CLIENT_ID")
    notion_client_secret: str | None = Field(default=None, alias="NOTION_CLIENT_SECRET")
    notion_oauth_redirect_uri: str = Field(default="http://localhost:8000/integrations/notion/callback", alias="NOTION_OAUTH_REDIRECT_URI")
    microsoft_client_id: str | None = Field(default=None, alias="MICROSOFT_CLIENT_ID")
    microsoft_client_secret: str | None = Field(default=None, alias="MICROSOFT_CLIENT_SECRET")
    microsoft_oauth_redirect_uri: str = Field(default="http://localhost:8000/integrations/microsoft/callback", alias="MICROSOFT_OAUTH_REDIRECT_URI")
    outlook_oauth_redirect_uri: str = Field(default="http://localhost:8000/integrations/outlook/callback", alias="OUTLOOK_OAUTH_REDIRECT_URI")
    onedrive_oauth_redirect_uri: str = Field(default="http://localhost:8000/integrations/onedrive/callback", alias="ONEDRIVE_OAUTH_REDIRECT_URI")
    canvas_client_id: str | None = Field(default=None, alias="CANVAS_CLIENT_ID")
    canvas_client_secret: str | None = Field(default=None, alias="CANVAS_CLIENT_SECRET")
    canvas_oauth_redirect_uri: str = Field(default="http://localhost:8000/integrations/canvas/callback", alias="CANVAS_OAUTH_REDIRECT_URI")
    moodle_client_id: str | None = Field(default=None, alias="MOODLE_CLIENT_ID")
    moodle_client_secret: str | None = Field(default=None, alias="MOODLE_CLIENT_SECRET")
    moodle_base_url: str | None = Field(default=None, alias="MOODLE_BASE_URL")
    moodle_oauth_redirect_uri: str = Field(default="http://localhost:8000/integrations/moodle/callback", alias="MOODLE_OAUTH_REDIRECT_URI")
    calendar_provider: str = Field(default="google", alias="CALENDAR_PROVIDER")
    gmail_provider: str = Field(default="google", alias="GMAIL_PROVIDER")
    drive_provider: str = Field(default="google", alias="DRIVE_PROVIDER")
    news_provider: str | None = Field(default=None, alias="NEWS_PROVIDER")
    news_api_key: str | None = Field(default=None, alias="NEWS_API_KEY")
    news_api_base_url: str | None = Field(default="https://newsapi.org/v2", alias="NEWS_API_BASE_URL")
    news_api_host: str | None = Field(default=None, alias="NEWS_API_HOST")
    news_default_region: str = Field(default="IN", alias="NEWS_DEFAULT_REGION")
    news_default_language: str = Field(default="en", alias="NEWS_DEFAULT_LANGUAGE")
    news_max_items: int = Field(default=8, alias="NEWS_MAX_ITEMS")
    weather_provider: str | None = Field(default=None, alias="WEATHER_PROVIDER")
    weather_api_key: str | None = Field(default=None, alias="WEATHER_API_KEY")
    weather_api_base_url: str | None = Field(default="https://api.openweathermap.org/data/2.5", alias="WEATHER_API_BASE_URL")
    weather_default_location: str = Field(default="Hyderabad, IN", alias="WEATHER_DEFAULT_LOCATION")
    weather_default_units: str = Field(default="metric", alias="WEATHER_DEFAULT_UNITS")
    search_provider: str | None = Field(default=None, alias="SEARCH_PROVIDER")
    search_api_key: str | None = Field(default=None, alias="SEARCH_API_KEY")
    search_api_base_url: str | None = Field(default=None, alias="SEARCH_API_BASE_URL")
    search_max_results: int = Field(default=8, alias="SEARCH_MAX_RESULTS")
    market_provider: str | None = Field(default=None, alias="MARKET_PROVIDER")
    market_api_key: str | None = Field(default=None, alias="MARKET_API_KEY")
    market_api_base_url: str | None = Field(default=None, alias="MARKET_API_BASE_URL")
    maps_provider: str | None = Field(default=None, alias="MAPS_PROVIDER")
    maps_api_key: str | None = Field(default=None, alias="MAPS_API_KEY")
    maps_api_base_url: str | None = Field(default=None, alias="MAPS_API_BASE_URL")
    rapidapi_key: str | None = Field(default=None, alias="RAPIDAPI_KEY")
    rapidapi_news_provider: str = Field(default="google-news13", alias="RAPIDAPI_NEWS_PROVIDER")
    rapidapi_news_host: str = Field(default="google-news13.p.rapidapi.com", alias="RAPIDAPI_NEWS_HOST")
    rapidapi_news_base_url: str = Field(default="https://google-news13.p.rapidapi.com", alias="RAPIDAPI_NEWS_BASE_URL")
    rapidapi_news_language: str = Field(default="en-US", alias="RAPIDAPI_NEWS_LANGUAGE")
    rapidapi_news_region: str = Field(default="US", alias="RAPIDAPI_NEWS_REGION")
    rapidapi_news_max_items: int = Field(default=8, alias="RAPIDAPI_NEWS_MAX_ITEMS")
    rapidapi_news_search_paths_raw: str = Field(default="/search", alias="RAPIDAPI_NEWS_SEARCH_PATHS")
    rapidapi_news_latest_paths_raw: str = Field(default="/latest", alias="RAPIDAPI_NEWS_LATEST_PATHS")
    rapidapi_news_category_paths_raw: str = Field(default="/{category}", alias="RAPIDAPI_NEWS_CATEGORY_PATHS")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]

    @property
    def rapidapi_news_search_paths(self) -> list[str]:
        return [path.strip() for path in self.rapidapi_news_search_paths_raw.split(",") if path.strip()]

    @property
    def rapidapi_news_latest_paths(self) -> list[str]:
        return [path.strip() for path in self.rapidapi_news_latest_paths_raw.split(",") if path.strip()]

    @property
    def rapidapi_news_category_paths(self) -> list[str]:
        return [path.strip() for path in self.rapidapi_news_category_paths_raw.split(",") if path.strip()]

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value


settings = Settings()
