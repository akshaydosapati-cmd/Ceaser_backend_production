import json
from pathlib import Path

from pydantic import AliasChoices
from pydantic import Field
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = Field(default="development", alias="CEASER_ENV")

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
    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")
    # OpenAI is CEASER's primary generation provider. The ordered list is used
    # by every production generation path; later providers are failover only.
    llm_provider_order_raw: str = Field(default="nvidia,huggingface,openai,groq,gemini", alias="LLM_PROVIDER_ORDER")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    nvidia_api_key: str | None = Field(default=None, alias="NVIDIA_API_KEY")
    nvidia_base_url: str = Field(default="https://integrate.api.nvidia.com/v1", alias="NVIDIA_BASE_URL")
    nvidia_model: str = Field(default="nvidia/nemotron-3-ultra-550b-a55b", alias="NVIDIA_MODEL")
    nvidia_enable_thinking: bool = Field(default=False, alias="NVIDIA_ENABLE_THINKING")
    nvidia_timeout_seconds: float = Field(default=120.0, alias="NVIDIA_TIMEOUT_SECONDS")
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    huggingface_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("HUGGINGFACE_API_KEY", "HF_TOKEN"),
    )
    groq_model: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL")
    huggingface_model: str = Field(
        default="mistralai/Devstral-Small-2507",
        validation_alias=AliasChoices("HUGGINGFACE_MODEL", "HF_MODEL"),
    )
    huggingface_coding_models_raw: str = Field(
        default="Qwen/Qwen2.5-Coder-7B-Instruct,bigcode/starcoder2-3b,deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct",
        alias="HUGGINGFACE_CODING_MODELS",
    )
    huggingface_image_model: str = Field(default="black-forest-labs/FLUX.1-schnell", alias="HUGGINGFACE_IMAGE_MODEL")
    huggingface_image_models_raw: str = Field(
        default="black-forest-labs/FLUX.1-schnell,ByteDance/Hyper-SD",
        alias="HUGGINGFACE_IMAGE_MODELS",
    )
    huggingface_datasets_enabled: bool = Field(default=False, alias="HUGGINGFACE_DATASETS_ENABLED")
    huggingface_datasets_json: str = Field(default="[]", alias="HUGGINGFACE_DATASETS_JSON")
    huggingface_dataset_max_rows: int = Field(default=3, alias="HUGGINGFACE_DATASET_MAX_ROWS")
    huggingface_dataset_timeout_seconds: float = Field(default=5.0, alias="HUGGINGFACE_DATASET_TIMEOUT_SECONDS")
    huggingface_base_url: str = Field(
        default="https://router.huggingface.co/v1/chat/completions",
        validation_alias=AliasChoices("HUGGINGFACE_BASE_URL", "HF_BASE_URL"),
    )
    llm_connect_timeout_seconds: float = Field(default=10.0, alias="LLM_CONNECT_TIMEOUT_SECONDS")
    llm_first_token_timeout_seconds: float = Field(default=4.0, alias="LLM_FIRST_TOKEN_TIMEOUT_SECONDS")
    llm_total_timeout_seconds: float = Field(default=45.0, alias="LLM_TOTAL_TIMEOUT_SECONDS")
    llm_max_fallbacks: int = Field(default=3, alias="LLM_MAX_FALLBACKS")
    llm_disabled_models_raw: str = Field(default="", alias="LLM_DISABLED_MODELS")
    provider_circuit_breaker_seconds: int = Field(default=300, alias="PROVIDER_CIRCUIT_BREAKER_SECONDS")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")
    openai_json_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_JSON_MODEL")
    # Public web evidence is gathered through the configured search provider
    # (Serper in production) before OpenAI is asked to compose an answer.
    openai_web_search_enabled: bool = Field(default=False, alias="OPENAI_WEB_SEARCH_ENABLED")
    openai_web_search_model: str = Field(default="chat-latest", alias="OPENAI_WEB_SEARCH_MODEL")
    openai_embedding_model: str = Field(default="text-embedding-3-small", alias="OPENAI_EMBEDDING_MODEL")
    openai_embedding_dimension: int = Field(default=1536, alias="OPENAI_EMBEDDING_DIMENSION")
    openai_temperature: float = Field(default=0.3, alias="OPENAI_TEMPERATURE")
    openai_max_tokens: int = Field(default=1600, alias="OPENAI_MAX_TOKENS")
    openai_request_timeout_seconds: float = Field(default=8.0, alias="OPENAI_REQUEST_TIMEOUT_SECONDS")
    gemini_request_timeout_seconds: float = Field(default=22.0, alias="GEMINI_REQUEST_TIMEOUT_SECONDS")
    knowledge_use_pgvector: bool = Field(default=True, alias="KNOWLEDGE_USE_PGVECTOR")
    knowledge_auto_embed: bool = Field(default=True, alias="KNOWLEDGE_AUTO_EMBED")
    knowledge_hnsw_enabled: bool = Field(default=True, alias="KNOWLEDGE_HNSW_ENABLED")
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
    cloud_worker_poll_seconds: int = Field(default=3, alias="CLOUD_WORKER_POLL_SECONDS")
    cloud_worker_lease_seconds: int = Field(default=90, alias="CLOUD_WORKER_LEASE_SECONDS")
    cloud_job_max_attempts: int = Field(default=3, alias="CLOUD_JOB_MAX_ATTEMPTS")
    cloud_jobs_per_user: int = Field(default=3, alias="CLOUD_JOBS_PER_USER")
    cloud_job_max_runtime_seconds: int = Field(default=900, alias="CLOUD_JOB_MAX_RUNTIME_SECONDS")
    cloud_workspace_max_bytes: int = Field(default=104857600, alias="CLOUD_WORKSPACE_MAX_BYTES")
    cloud_artifact_max_bytes: int = Field(default=26214400, alias="CLOUD_ARTIFACT_MAX_BYTES")
    cloud_job_retention_days: int = Field(default=30, alias="CLOUD_JOB_RETENTION_DAYS")
    cloud_worker_id: str = Field(default="ceaser-cloud-worker", alias="CLOUD_WORKER_ID")
    sandbox_provider: str = Field(default="unavailable", alias="SANDBOX_PROVIDER")
    local_coding_enabled: bool = Field(default=True, alias="CEASER_LOCAL_CODING_ENABLED")
    cloud_coding_enabled: bool = Field(default=False, alias="CEASER_CLOUD_CODING_ENABLED")
    bolt_max_repair_attempts: int = Field(default=2, alias="CEASER_BOLT_MAX_REPAIR_ATTEMPTS")
    browser_max_steps: int = Field(default=25, alias="CEASER_BROWSER_MAX_STEPS")
    browser_action_timeout_seconds: int = Field(default=15, alias="CEASER_BROWSER_ACTION_TIMEOUT_SECONDS")
    browser_navigation_timeout_seconds: int = Field(default=30, alias="CEASER_BROWSER_NAVIGATION_TIMEOUT_SECONDS")
    sandbox_docker_image: str = Field(default="ghcr.io/ceaser-ai/bolt-sandbox:1", alias="SANDBOX_DOCKER_IMAGE")
    sandbox_network_mode: str = Field(default="none", alias="SANDBOX_NETWORK_MODE")
    sandbox_command_timeout_seconds: int = Field(default=120, alias="SANDBOX_COMMAND_TIMEOUT_SECONDS")
    sandbox_memory_mb: int = Field(default=512, alias="SANDBOX_MEMORY_MB")
    sandbox_cpu_limit: float = Field(default=1.0, alias="SANDBOX_CPU_LIMIT")
    sandbox_pids_limit: int = Field(default=128, alias="SANDBOX_PIDS_LIMIT")
    sandbox_max_output_bytes: int = Field(default=1048576, alias="SANDBOX_MAX_OUTPUT_BYTES")
    sandbox_max_files: int = Field(default=5000, alias="SANDBOX_MAX_FILES")
    sandbox_max_build_retries: int = Field(default=2, alias="SANDBOX_MAX_BUILD_RETRIES")
    device_gateway_poll_ms: int = Field(default=500, alias="DEVICE_GATEWAY_POLL_MS")
    device_gateway_heartbeat_seconds: int = Field(default=20, alias="DEVICE_GATEWAY_HEARTBEAT_SECONDS")
    device_gateway_offline_seconds: int = Field(default=60, alias="DEVICE_GATEWAY_OFFLINE_SECONDS")
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
    notion_webhook_verification_token: str | None = Field(default=None, alias="NOTION_WEBHOOK_VERIFICATION_TOKEN")
    github_app_id: str | None = Field(default=None, alias="GITHUB_APP_ID")
    github_app_name: str = Field(default="CEASER", alias="GITHUB_APP_NAME")
    github_client_id: str | None = Field(default=None, alias="GITHUB_CLIENT_ID")
    github_client_secret: str | None = Field(default=None, alias="GITHUB_CLIENT_SECRET")
    github_private_key: str | None = Field(default=None, alias="GITHUB_PRIVATE_KEY")
    github_redirect_uri: str = Field(default="http://localhost:8000/integrations/github/callback", alias="GITHUB_REDIRECT_URI")
    github_scopes_raw: str = Field(default="user:email", alias="GITHUB_SCOPES")
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
    search_engine_id: str | None = Field(default=None, alias="SEARCH_ENGINE_ID")
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
    razorpay_key_id: str | None = Field(default=None, alias="RAZORPAY_KEY_ID")
    razorpay_key_secret: str | None = Field(default=None, alias="RAZORPAY_KEY_SECRET")
    razorpay_webhook_secret: str | None = Field(default=None, alias="RAZORPAY_WEBHOOK_SECRET")
    razorpay_api_base_url: str = Field(default="https://api.razorpay.com/v1", alias="RAZORPAY_API_BASE_URL")
    razorpay_checkout_name: str = Field(default="CEASER", alias="RAZORPAY_CHECKOUT_NAME")
    razorpay_checkout_theme_color: str = Field(default="#6d4cff", alias="RAZORPAY_CHECKOUT_THEME_COLOR")
    razorpay_plan_map_raw: str = Field(default="{}", alias="RAZORPAY_PLAN_MAP_JSON")
    credit_free_monthly: int = Field(default=500, alias="CREDIT_FREE_MONTHLY")
    credit_pro_monthly: int = Field(default=5000, alias="CREDIT_PRO_MONTHLY")
    credit_referral_reward: int = Field(default=500, alias="CREDIT_REFERRAL_REWARD")
    credit_referral_monthly_cap: int = Field(default=10, alias="CREDIT_REFERRAL_MONTHLY_CAP")
    credit_costs_raw: str = Field(default='{"ai_conversation":2,"research":10,"agent_workflow":20,"bolt_development":30,"local_command":0}', alias="CREDIT_COSTS_JSON")
    admin_emails_raw: str = Field(default="", alias="ADMIN_EMAILS")

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

    @property
    def razorpay_plan_map(self) -> dict[str, dict[str, str]]:
        try:
            parsed = json.loads(self.razorpay_plan_map_raw or "{}")
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, dict):
            return {}
        normalized: dict[str, dict[str, str]] = {}
        for plan_code, intervals in parsed.items():
            if not isinstance(intervals, dict):
                continue
            normalized[str(plan_code).upper()] = {
                str(interval).lower(): str(plan_id)
                for interval, plan_id in intervals.items()
                if plan_id
            }
        return normalized


    @property
    def huggingface_coding_models(self) -> list[str]:
        models = [self.huggingface_model.strip()]
        models.extend(
            model.strip()
            for model in self.huggingface_coding_models_raw.split(",")
            if model.strip()
        )
        deduped: list[str] = []
        for model in models:
            if model not in deduped:
                deduped.append(model)
        return deduped

    @property
    def huggingface_image_models(self) -> list[str]:
        models = [self.huggingface_image_model.strip()]
        models.extend(model.strip() for model in self.huggingface_image_models_raw.split(",") if model.strip())
        return list(dict.fromkeys(model for model in models if model))

    @property
    def huggingface_datasets(self) -> list[dict[str, str]]:
        try:
            parsed = json.loads(self.huggingface_datasets_json or "[]")
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [
            {
                "dataset": str(item.get("dataset", "")).strip(),
                "config": str(item.get("config", "default")).strip() or "default",
                "split": str(item.get("split", "train")).strip() or "train",
            }
            for item in parsed
            if isinstance(item, dict) and str(item.get("dataset", "")).strip()
        ][:5]

    @property
    def credit_costs(self) -> dict[str, int]:
        try:
            parsed = json.loads(self.credit_costs_raw or "{}")
            return {str(key): max(0, int(value)) for key, value in parsed.items()}
        except (ValueError, TypeError, json.JSONDecodeError):
            return {"ai_conversation": 2, "research": 10, "agent_workflow": 20, "bolt_development": 30, "local_command": 0}


    @property
    def admin_emails(self) -> set[str]:
        return {email.strip().lower() for email in self.admin_emails_raw.split(",") if email.strip()}

    def production_configuration_errors(self) -> list[str]:
        """Return safe setting names that make a production web runtime unsafe."""
        if self.environment.strip().lower() != "production":
            return []

        errors: list[str] = []
        required = {
            "DATABASE_URL": self.database_url,
            "SUPABASE_URL": self.supabase_url,
            "SUPABASE_ANON_KEY": self.supabase_anon_key,
            "SUPABASE_SERVICE_ROLE_KEY": self.supabase_service_role_key,
            "JWT_SECRET": self.jwt_secret,
            "ENCRYPTION_MASTER_KEY": self.encryption_master_key,
            "FRONTEND_APP_URL": self.frontend_app_url,
        }
        errors.extend(name for name, value in required.items() if not value)
        if "localhost" in self.database_url or "127.0.0.1" in self.database_url:
            errors.append("DATABASE_URL(non-local)")
        if not self.cors_origins or any(
            "localhost" in origin or "127.0.0.1" in origin for origin in self.cors_origins
        ):
            errors.append("CORS_ORIGINS(non-local)")
        if "localhost" in self.frontend_app_url or "127.0.0.1" in self.frontend_app_url:
            errors.append("FRONTEND_APP_URL(non-local)")
        if self.dev_auth_bypass:
            errors.append("DEV_AUTH_BYPASS(false)")
        if not any((self.openai_api_key, self.groq_api_key, self.gemini_api_key)):
            errors.append("NORMAL_CHAT_PROVIDER_KEY")
        return sorted(set(errors))

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value


settings = Settings()
