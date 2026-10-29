# AI Employee OS

**Status:** Functional multi-tenant AI platform (development build)

AI Employee OS is a multi-tenant SaaS platform that acts as an all-in-one operating system for businesses, augmented with specialized AI agents. Businesses get company dashboards (CRM, Sales, Finance, HR, …) staffed by AI employees that can act through 61 tools — sending email, creating quotations, scheduling meetings, running reports — while a human team supervises through role-based access.

Live deployment: [https://code-celix-ai-employes-os.vercel.app](https://code-celix-ai-employes-os.vercel.app)

---

## Architecture

```
Browser (Next.js :3000)
   │  Supabase JWT + HTTPS
   ▼
FastAPI backend (:8000, uvicorn --reload)
   ├── API routers  (app/api/v1/**)
   ├── AI engine    (app/ai/**)      → model router → Google Gemini
   ├── Integrations (app/integrations/**)  → OAuth + env-key provider clients
   ├── Services     (app/services/**)      → workflow_service, email_service, …
   └── Workers      (workers/**)           → Celery + Redis (REDIS_URL)
   │
   └── PostgreSQL / Supabase (DATABASE_URL) — multi-tenant RLS via current_org_id()
```

- **Frontend:** Next.js (App Router) + React Query + Tailwind; auth via Supabase.
- **Backend:** FastAPI + SQLAlchemy; per-org tenancy enforced by RLS + `organization_id` filters.
- **AI:** Gemini model chain with automatic fallbacks; native tool-calling with an envelope fallback path.
- **Database:** PostgreSQL (Supabase) — 78 tables with Row Level Security enforcing multi-tenancy.

Full details: **[SYSTEM_SETUP.md](SYSTEM_SETUP.md)** (agents, tools, integrations, workers, workflows, configuration) and **[ARCHITECTURE.md](ARCHITECTURE.md)**.

---

## Prerequisites

- Node.js 20+ and npm
- Python 3.11+
- [Supabase CLI](https://supabase.com/docs/guides/cli) (`supabase start` for local DB)
- Redis (local install or Docker) — required for Celery workers and rate limiting

---

## Database setup

```bash
cd supabase
supabase start          # local Postgres + GoTrue + Studio
supabase db push        # apply migrations (supabase/migrations/**)
```

Migrations seed the default 11-role model (1 platform + 10 company; `0069` removed `Employee/User`), the dashboards and AI employees (`0059`/`0060`), enable RLS with `current_org_id()`, and create all 78 tables. Point `DATABASE_URL` in `backend/.env` at the local Postgres connection string Supabase prints (`supabase status`).

Seeding demo users (optional, dev only):

```bash
cd backend
python scripts/seed_demo_users.py
```

---

## Running the backend

```bash
cd backend
pip install -r requirements.txt
# configure .env (see SYSTEM_SETUP.md §9 for every key)
uvicorn app.main:app --reload --port 8000
```

Live: [https://code-celix-ai-employes-os.vercel.app](https://code-celix-ai-employes-os.vercel.app)

API docs at `http://localhost:8000/docs`. Health check: `GET /health`.

### Authentication

Backend endpoints verify Supabase-issued JWTs with a three-path strategy (`app/core/auth.py`):

1. Offline HS256 check against `SUPABASE_JWT_SECRET` (fast; legacy projects).
2. Fallback to the project's JWKS endpoint — verifies ES256/RS256 asymmetric keys, which is what current Supabase projects sign with.
3. Live GoTrue validation (`GET /auth/v1/user`) when no secret is configured.

### LLM configuration

- `DEFAULT_AI_MODEL=gemini-3.5-flash` with `AI_MODEL_FALLBACKS=gemini-3.5-flash-lite,gemini-3.1-flash-lite` (what this repo's `.env` runs; the shipped `backend/.env.example` still defaults to the more conservative `gemini-2.5-flash` + `gemini-2.5-flash-lite,gemini-2.0-flash-lite` chain).
- The Google AI key is the live provider; `OPENROUTER_API_KEY` is optional (widens the fallback pool).
- Model ids are also stored per-row on `ai_employees.model` — if Google retires a model id, both `.env` and that column must point at models that still respond.

### Security & access control

Three layers, enforced in this order on every chat endpoint (list / read / send / voice / stream / create):

1. **Authentication** — every endpoint requires a valid Supabase JWT (three-path verification above).
2. **Cross-tenant isolation** — every query filters `organization_id == caller's org` *before* any bypass runs, so a foreign conversation id 404s even for admins. Company Admin's "see all" applies only inside their own company. Backed by RLS on all 78 tables (`0052_rls_full.sql` → `organization_id = current_org_id()`).
3. **Department isolation** — non-admin users only see/create conversations bound to their department's AI employees (`chat_access.py`): Finance ↔ Finance Assistant/Accountant, HR ↔ HR Assistant, Sales ↔ Sales Assistant, etc. Company Admin, CEO, legacy Owner/Admin and platform Super Admin see all conversations in their org. Platform Super Admin additionally has cross-org views by design (platform oversight).

Covered by regression tests in `backend/tests/test_ai_chat_isolation.py` (department isolation, admin org scoping, cross-org 404s, the `create_conversation` gate).

---

## Running the workers

```bash
cd backend
celery -A workers.celery_app worker --loglevel=info --pool=solo
celery -A workers.celery_app beat --loglevel=info     # schedules: daily recurring invoices, hourly follow-ups
```

Redis must be running (`REDIS_URL`, default `redis://localhost:6379`). Without workers, async jobs (email send, document OCR, embeddings, reports) never run; without `beat`, the periodic chains (recurring invoices, stale-customer follow-up) never fire.

Docker alternative (API + worker + beat + Postgres + Redis in one go):

```bash
cd backend
docker compose up --build
```

---

## Running the frontend

```bash
cd frontend
npm install
npm run dev              # http://localhost:3000
```

Configure `frontend/.env.local` with `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY`. The frontend talks to the backend API on `:8000` and uses Supabase directly for auth.

---

## AI agents (14)

Registry: `backend/app/ai/agents/` — **12 specialists + the master coordinator**, plus a `general` fallback assistant used when nothing else matches (14 definitions in `ALL_AGENTS` + `DEFAULT_AGENT`). `resolve_agent(role)` matches an AI employee's role (exact match, then synonyms).

| Key | Display name | Focus |
|---|---|---|
| `master` | AI Manager (Master Coordinator) | Plans, decomposes and delegates to specialists; sends email directly |
| `sales` | Sales Agent | Leads, deals, CRM, quotations |
| `support` | Customer Support Agent | Tickets, CRM lookups, thread summaries |
| `hr` | HR Assistant | Employees, leave requests, tasks |
| `recruiter` | Recruiter | Candidates, interview scheduling |
| `finance` | Finance Manager | Invoices, expenses |
| `accountant` | AI Accountant | Full invoicing, PDFs, financial reports |
| `marketing` | Marketing Manager | Campaigns, email drafts |
| `content_writer` | Content Writer | Knowledge search, campaign content |
| `legal` | Legal Assistant | Contract/NDA/MSA review |
| `inventory` | Inventory Manager | Stock, suppliers |
| `procurement` | Procurement Assistant | Purchase orders, suppliers |
| `executive` | Executive Assistant | Meetings, approvals, exec reports |
| `general` | AI Employee (General Assistant) | Fallback when no agent matches the role |

**Delegation:** only the master has `delegate_task` — it hands self-contained sub-tasks to any specialist (never to itself), then synthesizes one combined answer. Each specialist runs as a full agent turn with its own tools.

**Agent picker:** in AI Chat, **Super Admin, Company Admin and CEO** can start a conversation with any agent (`canPickAllAgents` in `frontend/src/lib/agents.ts`). Every other role is fixed to its dashboard agent (`ROLE_TO_AGENT`).

---

## Dashboards & roles (14 dashboards, 11 human roles)

Each dashboard pre-binds an AI agent through `/dashboard/chat?agent=<key>`:

| Dashboard | Route | Accessible to | Default agent |
|---|---|---|---|
| Super Admin (platform) | `/dashboard/super-admin` | Super Admin | master |
| Company Admin | `/dashboard` | Company Admin, CEO | master |
| CEO / Executive | `/dashboard/executive` | CEO | executive |
| Sales | `/dashboard/sales` | Sales Manager, Sales Executive | sales |
| CRM | `/dashboard/crm` | Company Admin, Sales (M/E) | sales |
| HR | `/dashboard/hr` | HR Manager | hr |
| Finance | `/dashboard/finance` | Finance Manager, Accountant | finance / accountant |
| Customer Support | `/dashboard/support` | Customer Support | support |
| Marketing | `/dashboard/marketing` | Marketing Manager | marketing |
| Operations | `/dashboard/operations` | Operations Manager | inventory |
| Employee (personal) | `/dashboard/employee` | legacy `Employee` rows only | — |
| AI Employees | `/dashboard/employees` | Super Admin, Company Admin, CEO | per-employee |
| Reports & Analytics | `/dashboard/analytics` | Super Admin, Company Admin, CEO + all managers | — |
| Settings & Integrations | `/dashboard/settings` | Super Admin, Company Admin, CEO | — |

- **Super Admin** sees every dashboard (platform-wide, cross-tenant views).
- **Company Admin + CEO** see the full company set (everything except the platform dashboard).
- **Department roles** see exactly their own dashboards; **legacy `Owner`/`Admin`** rows map to Company Admin. The former `Employee/User` role was removed (migration 0069), which also dropped the seeded `Employee Dashboard` row — the personal dashboard survives in the frontend registry (`frontend/src/lib/dashboards.ts`) for legacy `Employee` members. Three legacy role names (`Owner`, `Admin`, `Employee`) still exist on pre-0069 orgs.
- Module gating: admins can disable modules per-org, which hides the matching dashboards.

Full matrix incl. which agent answers each chat: **[DASHBOARD_MATRIX.md](DASHBOARD_MATRIX.md)**.

---

## AI tools (61)

`backend/app/ai/tools/` — organized by domain:

| Domain | Examples |
|---|---|
| CRM | `search_crm`, `get_customer`, `list_leads`, `list_deals`, `create_activity` |
| Email | `send_email`, `send_quotation_email` (real send via org's connected Gmail) |
| Marketing | `list_campaigns`, `create_email_draft`, `classify_email_thread` |
| Tasks / Reminders | `list_tasks`, `create_task`, `create_reminder`, `list_reminders` |
| Calendar | `list_meetings`, `create_meeting`, `summarize_meeting`, `transcribe_meeting_audio` |
| HR | `list_employees`, `list_leave_requests`, `list_candidates` |
| Invoicing | `create_invoice`, `mark_invoice_paid`, `generate_invoice_pdf_tool`, `generate_invoice_payment_link` (Stripe) |
| Quotations | `create_quotation`, `approve_quotation`, `reject_quotation`, `submit_quotation_for_approval` |
| Knowledge / Docs | `search_knowledge` (RAG + pgvector), `get_document`, `analyze_document` |
| Reporting | `generate_revenue_report`, `generate_sales_pipeline_report`, `generate_forecast_report`, … |
| Integrations | `slack_post_message`, `zoho_create_lead`, `xero_create_invoice`, `drive_upload_file`, `sheets_append_row`, `onedrive_upload_file` |
| Delegation | `delegate_task` (master only) |

Guardrails: a safe-tool allowlist (`_SAFE_TOOL_NAMES` in `app/ai/guardrails.py`) blocks dangerous tool calls.

The complete tool-by-tool registry with per-agent counts lives in **SYSTEM_SETUP.md §4**.

---

## External integrations (13)

- **OAuth (per-org encrypted tokens):** Gmail, Google Calendar, Google Drive, Google Sheets (shared Google callback); Outlook, Microsoft 365, OneDrive (shared Microsoft callback); Slack, Zoho, Xero.
- **Env-key:** WhatsApp, Stripe, Cloudflare R2.
- Console/callback URLs: **[INTEGRATION_SETUP.md](INTEGRATION_SETUP.md)**.

---

## Feature status & known gaps

- **Workflows page** is a read-only view of the `workflows` table — the drag-drop builder and the execution engine are *not implemented* (the placeholder button was removed). Real automation runs as built-in Celery chains: invoice-paid workflow, hourly stale-customer follow-up, daily recurring invoices, email cascade.
- **Settings → API Keys** was removed from the UI. The `api_keys` table and CRUD endpoints exist, but no key-verification middleware is wired yet — keys cannot authenticate anything today.
- Redis-backed rate limiting falls back to in-memory when Redis is down (per-request latency increases; restart Redis to clear).

---

## Documentation

- **[SYSTEM_SETUP.md](SYSTEM_SETUP.md)** — *maintained*: agents, tools, integrations, workers, workflows, and configuration.
- **[DASHBOARD_MATRIX.md](DASHBOARD_MATRIX.md)** — *maintained*: which AI agent works with which dashboard, and which human role can access which dashboards.
- **INTEGRATION_SETUP.md** — callback/webhook URLs for every provider console.
- `ARCHITECTURE.md`, `API_SPEC.md`, `PRD.md`, `DESIGN.md`.
- `CURRENT_STATE.md` / `BACKEND_GAP_ANALYSIS.md` / `AUDIT_REPORT.md` — historical snapshots, superseded by `SYSTEM_SETUP.md`.
