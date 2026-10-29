# AI Employee OS — Backend API & Services

FastAPI-powered backend service for the **AI Employee OS** platform. Provides multi-tenant REST APIs, real-time AI agent execution (Gemini / OpenRouter), background Celery workers, and external service integrations.

---

## Tech Stack & Architecture

- **Framework:** FastAPI (Python 3.11+) with Uvicorn
- **ORM / Database:** SQLAlchemy 2.0 + PostgreSQL (Supabase with RLS & pgvector)
- **Asynchronous Workers:** Celery + Redis
- **AI Engine:** Google Gemini (`gemini-3.5-flash` with automatic fallback chains) & optional OpenRouter support
- **Auth:** Supabase JWT validation (HS256 offline secret / JWKS asymmetric keys / live GoTrue)
- **External Integrations:** Google Workspace (Gmail, Drive, Sheets, Calendar), Microsoft 365 / Outlook / OneDrive, Slack, Zoho CRM, Xero, Stripe, WhatsApp, Cloudflare R2

---

## Directory Structure

```text
backend/
├── app/
│   ├── ai/                # AI agent registry, model router, prompts, tools & guardrails
│   ├── api/v1/            # API endpoints & route handlers
│   ├── core/              # Config, DB session engine, auth & logging
│   ├── integrations/      # Third-party OAuth & API provider clients
│   ├── middleware/        # Audit, rate limiting, and request logging middleware
│   ├── models/            # SQLAlchemy database models
│   ├── schemas/           # Pydantic request/response schemas
│   └── services/          # Business logic services (workflows, email, storage, etc.)
├── workers/               # Celery app, task queues, and beat periodic schedules
├── scripts/               # Seed scripts, migrations & maintenance utilities
├── tests/                 # Pytest test suite
├── Dockerfile             # Container definition for API and workers
├── docker-compose.yml     # Multi-container orchestration (API, worker, beat, Postgres, Redis)
└── requirements.txt       # Python dependencies
```

---

## Prerequisites

- **Python 3.11+**
- **PostgreSQL / Supabase** (with `pgvector` extension enabled)
- **Redis** (running locally on port 6379 or via Docker)

---

## Environment Setup

1. Copy the template environment file:
   ```bash
   cp .env.example .env
   ```
2. Configure the required variables in `.env`:
   - `DATABASE_URL`: Connection string (`postgresql+psycopg2://...`)
   - `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`
   - `ENCRYPTION_KEY`: Used to encrypt tenant integration tokens:
     ```bash
     python -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
     ```
   - `GOOGLE_AI_KEY` (and optionally `OPENROUTER_API_KEY`)
   - `REDIS_URL`: Defaults to `redis://localhost:6379/0`

For the complete catalog of configuration options, refer to `SYSTEM_SETUP.md`.

---

## Installation & Running Locally

1. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   # Linux/macOS:
   source venv/bin/activate
   # Windows:
   .\venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Start the FastAPI application:**
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   - API Server: `http://localhost:8000`
   - Interactive Swagger docs: `http://localhost:8000/docs`
   - OpenAPI spec: `http://localhost:8000/openapi.json`
   - Health check: `GET http://localhost:8000/health`

---

## Running Celery Workers & Periodic Tasks

Background tasks (email dispatch, OCR, document embeddings, PDF reports) and scheduled jobs (recurring invoices, customer follow-up) require Celery workers and Celery Beat:

```bash
# In a separate terminal (Worker):
celery -A workers.celery_app worker --loglevel=info --pool=solo

# In another terminal (Beat Scheduler):
celery -A workers.celery_app beat --loglevel=info
```

---

## Running with Docker Compose

To run the complete backend stack (FastAPI, Celery worker, Celery beat, PostgreSQL, and Redis) in containers:

```bash
docker compose up --build
```

---

## Testing

Run tests with `pytest`:

```bash
pytest
```
Run tenancy and isolation regression tests:
```bash
pytest tests/test_ai_chat_isolation.py
```

