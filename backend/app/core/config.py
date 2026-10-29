"""Application configuration loaded from environment files.

Secrets are read once at import time from ``.env`` (preferred) or ``env``
(the file currently shipped in the repo).  Never ``print()`` or log any of
these values.
"""
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "AI Employee OS"
    ENVIRONMENT: str = "development"
    VERSION: str = "1.0.0"

    # ---------------------------------------------------------------- database
    DATABASE_URL: str

    # ---------------------------------------------------------------- supabase
    # Empty defaults keep import-time Settings() from crashing in CI, where
    # only DATABASE_URL is provided. Production always sets these via .env;
    # the auth/user services fail per-request with a clear error if empty.
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""

    # ---------------------------------------------------------------- jwt
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Fernet key source for encrypting sensitive DB fields at rest
    # (integration tokens, webhook secrets, SSO client secrets).
    ENCRYPTION_KEY: str = ""

    # ---------------------------------------------------------------- ai / llm
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    # When true, OpenAI/Anthropic/Google completions that would fail because
    # the matching direct provider key is missing or invalid will silently retry
    # through OpenRouter when OPENROUTER_API_KEY is configured. This lets a
    # single OpenRouter key cover the whole fallback chain without requiring a
    # key for every provider.
    #
    # When false (default), those providers fail the normal way so a
    # missing/invalid key produces a loud, fast error instead of a silent retry.
    OPENROUTER_AUTO_FALLBACK: bool = False
    # OpenRouter is the primary gateway and already routes catalog models (vendor
    # prefixes / ":free" variants) through the same API. OPENROUTER_AUTO_FALLBACK
    # extends that reach to direct OpenAI/Anthropic/Google model ids too.
    # Gemini 2.5 Flash/Pro support images (screenshots, attached photos) via
    # inline base64 parts — keep multimodal-capable models in the default chain.
    DEFAULT_AI_MODEL: str = "gemini-2.5-flash"
    # Cap generated tokens per LLM call. Kept conservative so free-tier
    # OpenRouter limits (e.g. ~1-4k max_tokens depending on prompt size) are
    # respected; raise it when credits are added.
    AI_MAX_TOKENS: int = 1024
    # Comma-separated backup model ids tried in order when the primary model
    # fails with a retryable provider error (402 no-credits / 429 rate-limit /
    # 5xx). Free OpenRouter models are transiently rate-limited, so a chain of
    # several keeps chat working without paid credits.
    AI_MODEL_FALLBACKS: str = ""
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536
    # Used when GOOGLE_AI_KEY is set and OPENAI_API_KEY is not (Google
    # embeddings output 1536 dims via outputDimensionality, matching the
    # pgvector columns created for the OpenAI model).
    GOOGLE_EMBEDDING_MODEL: str = "gemini-embedding-001"

    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    GOOGLE_AI_KEY: Optional[str] = None

    # ---------------------------------------------------------------- infra
    REDIS_URL: str = "redis://localhost:6379"
    FRONTEND_ORIGIN: str = "http://localhost:3000"

    # ---------------------------------------------------------------- integrations
    STRIPE_SECRET_KEY: Optional[str] = None
    # Webhook signing secrets. Each Stripe webhook endpoint has its OWN secret:
    #   - STRIPE_WEBHOOK_SECRET        -> /api/v1/invoices/stripe-webhook (checkout.session.completed)
    #   - STRIPE_BILLING_WEBHOOK_SECRET -> /api/v1/billing/stripe/webhook (customer.subscription.*)
    # The billing one falls back to STRIPE_WEBHOOK_SECRET when only one is set.
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    STRIPE_BILLING_WEBHOOK_SECRET: Optional[str] = None
    # OAuth callback paths MUST match a backend route. Google-family services
    # (Gmail/Calendar/Drive/Sheets) share ONE callback URL — /oauth/callback/google —
    # and Microsoft-family services (Outlook/M365/OneDrive) share ONE —
    # /oauth/callback/microsoft. The real provider is encoded in the OAuth
    # state token and resolved on the way back. Slack/Zoho/Xero keep their own.
    GMAIL_CLIENT_ID: Optional[str] = None
    GMAIL_CLIENT_SECRET: Optional[str] = None
    GMAIL_REDIRECT_URI: str = "http://localhost:8000/api/v1/integrations/oauth/callback/google"
    OUTLOOK_CLIENT_ID: Optional[str] = None
    OUTLOOK_CLIENT_SECRET: Optional[str] = None
    OUTLOOK_REDIRECT_URI: str = "http://localhost:8000/api/v1/integrations/oauth/callback/microsoft"
    MICROSOFT_CLIENT_ID: Optional[str] = None
    MICROSOFT_CLIENT_SECRET: Optional[str] = None
    MICROSOFT_REDIRECT_URI: str = "http://localhost:8000/api/v1/integrations/oauth/callback/microsoft"
    GOOGLE_CAL_CLIENT_ID: Optional[str] = None
    GOOGLE_CAL_CLIENT_SECRET: Optional[str] = None
    GOOGLE_CAL_REDIRECT_URI: str = "http://localhost:8000/api/v1/integrations/oauth/callback/google"
    SLACK_CLIENT_ID: Optional[str] = None
    SLACK_CLIENT_SECRET: Optional[str] = None
    SLACK_REDIRECT_URI: str = "http://localhost:8000/api/v1/integrations/oauth/callback/slack"
    # Bot token from Slack app > OAuth & Permissions. Used as the posting
    # credential when an org hasn't connected Slack via OAuth yet, so
    # invoice-paid notifications and the slack_post_message tool work
    # out of the box (best-effort fallback; the per-org OAuth token wins).
    SLACK_BOT_TOKEN: Optional[str] = None
    # Google Drive / Sheets reuse the same Google OAuth client (GMAIL_*) — only
    # scopes differ, so they share the family callback URL too.
    GOOGLE_DRIVE_REDIRECT_URI: str = "http://localhost:8000/api/v1/integrations/oauth/callback/google"
    GOOGLE_SHEETS_REDIRECT_URI: str = "http://localhost:8000/api/v1/integrations/oauth/callback/google"
    # OneDrive / Excel reuse the same Microsoft OAuth client (MICROSOFT_*).
    ONEDRIVE_REDIRECT_URI: str = "http://localhost:8000/api/v1/integrations/oauth/callback/microsoft"
    # Zoho CRM (OAuth 2.0). Accounts/data hosts can be region-specific
    # (zoho.eu / zoho.in / zoho.com.au) — override when needed. The data
    # center must match where the OAuth client was created AND where the
    # signed-in Zoho account lives (zoho.com = US/global, zoho.eu, zoho.in,
    # zoho.com.au, zoho.jp, zoho.sa).
    ZOHO_CLIENT_ID: Optional[str] = None
    ZOHO_CLIENT_SECRET: Optional[str] = None
    ZOHO_REDIRECT_URI: str = "http://localhost:8000/api/v1/integrations/oauth/callback/zoho"
    ZOHO_DATA_CENTER: str = "com"
    # Empty by design: the per-data-center resolver in
    # app/integrations/zoho/service.py picks the API base from ZOHO_DATA_CENTER.
    # Only set this to force a custom CRM endpoint.
    ZOHO_API_BASE_URL: str = ""
    # Xero accounting (OAuth 2.0, HTTP-Basic token endpoint).
    # The scope list MUST match what is enabled on the Xero app
    # (developer.xero.com > My Apps > app), or Xero shows "invalid_scope" on
    # its own authorize page. Newer Xero apps use granular scopes — use
    # ``accounting.invoices`` (NOT the legacy ``accounting.transactions``),
    # and include ``offline_access`` for refresh tokens.
    XERO_CLIENT_ID: Optional[str] = None
    XERO_CLIENT_SECRET: Optional[str] = None
    XERO_REDIRECT_URI: str = "http://localhost:8000/api/v1/integrations/oauth/callback/xero"
    XERO_SCOPES: str = (
        "openid profile email "
        "accounting.invoices accounting.contacts accounting.settings offline_access"
    )
    WHATSAPP_API_TOKEN: Optional[str] = None
    WHATSAPP_PHONE_ID: Optional[str] = None
    WHATSAPP_VERIFY_TOKEN: str = ""
    ACCOUNTING_BASE_URL: Optional[str] = None
    ACCOUNTING_API_KEY: Optional[str] = None

    # ------------------------------------------------------------ cloud storage
    # File storage backend: "local" (default) | "s3" | "r2". When s3/r2 is
    # set, generated PDFs/QRs/uploads are mirrored to the bucket (write-through;
    # a local cache keeps existing /documents/ serving working).
    STORAGE_PROVIDER: str = "local"
    S3_ENDPOINT_URL: Optional[str] = None
    S3_REGION: str = "auto"
    S3_ACCESS_KEY_ID: Optional[str] = None
    S3_SECRET_ACCESS_KEY: Optional[str] = None
    S3_BUCKET: Optional[str] = None

    # ---------------------------------------------------------------- observability
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 600
    AUDIT_LOG_ENABLED: bool = True

    model_config = SettingsConfigDict(
        env_file=(".env", "env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()